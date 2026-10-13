"""Chargement mensuel des CSV via l'API SQL, sans dependance supplementaire."""

import csv
import json
import logging
import re
import time
import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Structure cible ; discount_percent exige la migration SQL fournie (remises 3.5%).
SCHEMAS = {
    "tickets": list(zip(
        "ticket_id ticket_type sale_timestamp customer_name ticket_total_ttc seller_name seller_id calculated_total_ttc total_difference article_count payment_methods source_month source_file source_row_number".split(),
        "bigint string timestamp string double string bigint double double bigint string date string bigint".split(),
    )),
    "sales_lines": list(zip(
        "ticket_id ticket_type sale_timestamp customer_name seller_id product_code product_label_raw quantity unit_price_ttc discount_percent vat_rate gross_amount_ttc discount_amount_ttc net_amount_ttc source_month source_file source_row_number".split(),
        "bigint string timestamp string bigint bigint string double double decimal(24,4) double double double double date string bigint".split(),
    )),
}
TABLES = {"tickets": "raw_tickets", "sales_lines": "raw_sales_lines"}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Identifiant SQL invalide.")
    return f"`{value}`"


class SqlClient:
    def __init__(self, connection):
        host = (connection.host or "").strip().removeprefix("https://").rstrip("/")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+\.cloud\.databricks\.com", host):
            raise ValueError("Hostname Databricks AWS invalide.")
        self.token = connection.password
        if not self.token:
            raise ValueError("Token manquant dans la connexion Airflow.")
        extra = connection.extra_dejson
        match = re.fullmatch(r"/sql/1\.0/warehouses/([A-Za-z0-9]+)", extra.get("http_path", ""))
        if not match:
            raise ValueError("http_path invalide dans Extra.")
        self.warehouse = match.group(1)
        self.prefix = identifier(extra.get("catalog", "workspace")) + "." + identifier(extra.get("schema", "boucherie_raw"))
        self.url = f"https://{host}/api/2.0/sql/statements"

    def request(self, path, payload=None):
        request = Request(
            self.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"Databricks HTTP {exc.code}. Verifier connexion et autorisations.") from None
        except (URLError, TimeoutError):
            # Ne pas reenvoyer aveuglement une ecriture dont la reponse a ete perdue.
            raise RuntimeError("Connexion Databricks interrompue. Consulter Query History avant relance.") from None

    def execute(self, statement, parameters=None):
        payload = {
            "warehouse_id": self.warehouse, "statement": statement,
            "wait_timeout": "10s", "disposition": "INLINE", "format": "JSON_ARRAY",
        }
        if parameters:
            payload["parameters"] = parameters
        result = self.request("", payload)
        statement_id = result.get("statement_id")
        deadline = time.monotonic() + 600
        while result["status"]["state"] in ("PENDING", "RUNNING"):
            if time.monotonic() > deadline:
                self.request(f"/{statement_id}/cancel", {})
                raise TimeoutError(f"Requete Databricks trop longue : {statement_id}")
            time.sleep(5)
            result = self.request(f"/{statement_id}")
        if result["status"]["state"] != "SUCCEEDED":
            code = result["status"].get("error", {}).get("error_code", "UNKNOWN")
            raise RuntimeError(f"Echec Databricks {code}, requete {statement_id}. Voir Query History.")
        if result.get("manifest", {}).get("truncated") or result.get("result", {}).get("next_chunk_index") is not None:
            raise RuntimeError("Resultat SQL incomplet.")
        return result.get("result", {}).get("data_array", [])


def normalize_value(value, kind, column):
    if value is None:
        raise ValueError(f"Cellule absente : {column}")
    if kind == "string":
        return value
    if value == "":
        return None
    if kind in ("bigint", "double", "decimal(24,4)"):
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError(f"Nombre non fini : {column}")
        if kind == "decimal(24,4)":
            if abs(number) >= Decimal("1E20") or number != number.quantize(Decimal("0.0001")):
                raise ValueError(f"Decimal hors precision : {column}")
            return str(number)
        if kind == "bigint":
            if number != number.to_integral_value() or not -(2**63) <= number < 2**63:
                raise ValueError(f"Entier invalide : {column}")
            return str(int(number))
        if abs(number) > Decimal("1.7976931348623157E308"):
            raise ValueError(f"Double hors limites : {column}")
        return str(number)
    if kind == "date":
        normalized = value + "-01" if re.fullmatch(r"\d{4}-\d{2}", value) else value
        parsed = date.fromisoformat(normalized)
        if parsed.day != 1:
            raise ValueError("source_month doit etre le premier jour du mois.")
        return parsed.isoformat()
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        raise ValueError("Le timestamp de caisse doit etre sans fuseau horaire.")
    return parsed.isoformat(sep=" ")


def read_manifest(manifest, output_root):
    """Valider tous les CSV avant tout acces en ecriture a Databricks."""
    data = {kind: [] for kind in SCHEMAS}
    seen_files = set()
    seen_keys = {kind: set() for kind in SCHEMAS}
    for entry in manifest:
        kind = entry["kind"]
        if kind == "rejects":
            continue
        if kind not in SCHEMAS:
            raise ValueError("Type de CSV inconnu.")
        path = Path(entry["path"]).resolve()
        if not path.is_relative_to(Path(output_root).resolve()) or path in seen_files:
            raise ValueError("Chemin CSV invalide ou duplique.")
        seen_files.add(path)
        expected_name = re.fullmatch(rf"{kind}_(\d{{4}})_(\d{{2}})\.csv", path.name)
        if not expected_name:
            raise ValueError("Nom de CSV invalide.")
        month = date(int(expected_name[1]), int(expected_name[2]), 1).isoformat()
        count = 0
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != [name for name, _ in SCHEMAS[kind]]:
                raise ValueError(f"Colonnes incorrectes : {path.name}")
            for line_number, row in enumerate(reader, 2):
                try:
                    if None in row:
                        raise ValueError("Colonnes supplementaires")
                    row = {name: normalize_value(row[name], datatype, name) for name, datatype in SCHEMAS[kind]}
                    if row["source_month"] != month:
                        raise ValueError("Mois du fichier et de la ligne differents")
                    if not row["source_file"] or row["source_row_number"] is None or row["ticket_id"] is None:
                        raise ValueError("Cle de provenance ou ticket manquant")
                    key = (row["source_month"], row["source_file"], row["source_row_number"])
                    if key in seen_keys[kind]:
                        raise ValueError("Ligne de provenance dupliquee")
                    seen_keys[kind].add(key)
                except (ValueError, ArithmeticError) as exc:
                    raise ValueError(f"CSV invalide {path.name}, ligne {line_number}: {exc}") from None
                data[kind].append(row)
                count += 1
        if count != entry["rows"] or count == 0:
            raise ValueError(f"CSV vide ou nombre de lignes incorrect : {path.name}")
    counts = {kind: dict(Counter(row["source_month"] for row in rows)) for kind, rows in data.items()}
    if not counts["tickets"] or counts["tickets"].keys() != counts["sales_lines"].keys():
        raise ValueError("Les deux types de CSV doivent couvrir les memes mois, sans etre vides.")
    return data, counts


def month_counts(client, table, predicate="true"):
    return {month: int(count) for month, count in client.execute(
        f"SELECT CAST(source_month AS STRING), COUNT(*) FROM {table} WHERE {predicate} GROUP BY source_month"
    )}


def load_csvs(manifest, output_root, client):
    data, counts = read_manifest(manifest, output_root)
    stages = {}
    suffix = uuid.uuid4().hex
    try:
        # Controler les DEUX cibles avant de commencer leur chargement.
        for kind, schema in SCHEMAS.items():
            target = f"{client.prefix}.{identifier(TABLES[kind])}"
            actual = [(row[0], row[1].lower()) for row in client.execute(f"DESCRIBE TABLE {target}") if row[0] and not row[0].startswith("#")]
            if actual[:len(schema)] != schema or any(name not in dict(schema) for name, _ in actual):
                raise ValueError(f"Structure inattendue pour {TABLES[kind]}. Verifier notamment la migration discount_percent vers DECIMAL(24,4) dans scripts/sql/001_discount_percent.sql.")
            detail = client.execute(f"DESCRIBE DETAIL {target}")
            if not detail or detail[0][0].lower() != "delta":
                raise ValueError("Le remplacement mensuel exige une table Delta.")

        for kind, schema in SCHEMAS.items():
            stage = f"{client.prefix}.`_airflow_load_{kind}_{suffix}`"
            stages[kind] = stage
            ddl = ", ".join(f"{identifier(name)} {datatype}" for name, datatype in schema)
            client.execute(f"CREATE TABLE {stage} ({ddl}) USING DELTA")
            # JSON parametre : accents, apostrophes et retours a la ligne restent des donnees.
            json_schema = "ARRAY<STRUCT<" + ",".join(f"{name}:STRING" for name, _ in schema) + ">>"
            projection = ", ".join(f"CAST(r.{identifier(name)} AS {datatype})" for name, datatype in schema)
            statement = f"INSERT INTO {stage} SELECT {projection} FROM (SELECT explode(from_json(:rows, '{json_schema}', map('mode', 'FAILFAST'))) AS r)"
            for start in range(0, len(data[kind]), 500):
                client.execute(statement, [{"name": "rows", "value": json.dumps(data[kind][start:start + 500], ensure_ascii=False)}])
            if month_counts(client, stage) != counts[kind]:
                raise ValueError(f"Comptage intermediaire incorrect : {kind}")
            logging.info("Lot %s prepare : %s lignes", kind, len(data[kind]))

        # Chaque remplacement est atomique pour UNE table, pas pour la paire.
        months = ", ".join(f"DATE '{month}'" for month in sorted(counts["tickets"]))
        predicate = f"source_month IN ({months})"
        for kind, schema in SCHEMAS.items():
            target = f"{client.prefix}.{identifier(TABLES[kind])}"
            columns = ", ".join(identifier(name) for name, _ in schema)
            client.execute(f"INSERT INTO {target} REPLACE WHERE {predicate} SELECT {columns} FROM {stages[kind]}")
            if month_counts(client, target, predicate) != counts[kind]:
                raise ValueError(f"Comptage final incorrect : {kind}. Relancer le chargement.")
            logging.info("%s charge et controle : %s", TABLES[kind], counts[kind])
        return counts
    finally:
        for stage in stages.values():
            try:
                client.execute(f"DROP TABLE IF EXISTS {stage}")
            except Exception:
                logging.warning("Table intermediaire a nettoyer apres verification des requetes : %s", stage)


def load_databricks(manifest):
    from airflow.hooks.base import BaseHook
    from airflow_pipeline import OUTPUT_ROOT

    return load_csvs(manifest, OUTPUT_ROOT, SqlClient(BaseHook.get_connection("databricks_boucherie")))
