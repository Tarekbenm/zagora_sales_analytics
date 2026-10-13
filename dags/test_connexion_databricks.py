"""Diagnostic manuel en lecture seule, via l'API SQL Databricks."""

from datetime import timedelta

import pendulum
from airflow.decorators import dag, task


@dag(
    dag_id="test_connexion_databricks",
    description="Verifier la connexion et compter les deux tables sources",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["boucherie", "diagnostic"],
)
def test_connexion_databricks():
    @task(execution_timeout=timedelta(minutes=12), retries=0)
    def verifier_acces():
        import json
        import logging
        import re
        import time
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        from airflow.hooks.base import BaseHook

        connection = BaseHook.get_connection("databricks_boucherie")
        host = (connection.host or "").strip().removeprefix("https://").rstrip("/")
        if not re.fullmatch(r"[a-zA-Z0-9.-]+\.cloud\.databricks\.com", host):
            raise ValueError("Host doit etre le hostname Databricks AWS, sans chemin.")
        if not connection.password:
            raise ValueError("Token manquant dans Password de databricks_boucherie.")
        extra = connection.extra_dejson
        match = re.fullmatch(r"/sql/1\.0/warehouses/([a-zA-Z0-9]+)", extra.get("http_path", ""))
        if not match:
            raise ValueError("http_path absent ou invalide dans Extra.")
        catalog = extra.get("catalog", "workspace")
        schema = extra.get("schema", "boucherie_raw")
        if not all(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name) for name in (catalog, schema)):
            raise ValueError("Nom de catalogue ou schema invalide.")

        def api(path, payload=None):
            request = Request(
                f"https://{host}/api/2.0/sql/statements{path}",
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Authorization": f"Bearer {connection.password}", "Content-Type": "application/json"},
            )
            try:
                with urlopen(request, timeout=45) as response:
                    return json.load(response)
            except HTTPError as exc:
                raise RuntimeError(f"Databricks HTTP {exc.code} : verifier token, warehouse et droits.") from None
            except URLError:
                raise RuntimeError("Databricks inaccessible : verifier reseau et hostname.") from None

        prefix = f"`{catalog}`.`{schema}`"
        result = api("", {
            "warehouse_id": match.group(1),
            "statement": (
                f"SELECT 'raw_tickets' AS table_name, COUNT(*) AS nombre_lignes FROM {prefix}.raw_tickets "
                f"UNION ALL SELECT 'raw_sales_lines', COUNT(*) FROM {prefix}.raw_sales_lines"
            ),
            "wait_timeout": "10s",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
        })
        statement_id = result.get("statement_id")
        deadline = time.monotonic() + 600
        while result["status"]["state"] in ("PENDING", "RUNNING"):
            if time.monotonic() >= deadline:
                api(f"/{statement_id}/cancel", {})
                raise TimeoutError("Le warehouse n'a pas termine le test en dix minutes.")
            time.sleep(10)
            result = api(f"/{statement_id}")
        if result["status"]["state"] != "SUCCEEDED":
            error = result["status"].get("error", {})
            raise RuntimeError(f"Echec SQL Databricks : {error.get('error_code', result['status']['state'])}. Consulter Query History dans Databricks.")
        rows = result.get("result", {}).get("data_array", [])
        counts = {name: int(count) for name, count in rows}
        if set(counts) != {"raw_tickets", "raw_sales_lines"}:
            raise RuntimeError("Resultat du comptage incomplet.")
        for name, count in counts.items():
            logging.info("%s.%s.%s : %s lignes", catalog, schema, name, count)
        return counts

    verifier_acces()


test_connexion_databricks()
