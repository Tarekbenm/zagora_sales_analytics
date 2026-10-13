"""Adaptation du parseur existant, avec sorties isolees par execution Airflow."""

import csv
import hashlib
import logging
from datetime import datetime
from pathlib import Path

import normalize_excel as parser


OUTPUT_ROOT = parser.PROJECT_DIR / "data" / "airflow_runs"
SCHEMAS = {
    "tickets": parser.TICKET_COLUMNS,
    "sales_lines": parser.ARTICLE_COLUMNS,
    "rejects": parser.REJECT_COLUMNS,
}


def check_sources():
    sources = parser.find_source_files()
    for source in sources:
        datetime.strptime(source.stem, "%Y_%m")
        with source.open("rb") as handle:
            if not handle.read(1):
                raise ValueError(f"Fichier Excel vide : {source.name}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    logging.info("%s fichiers Excel detectes", len(sources))
    return [source.name for source in sources]


def normalize_sources(sources, run_id):
    # Un identifiant compatible Windows/Linux, stable lors des retries.
    output_dir = OUTPUT_ROOT / hashlib.sha256(run_id.encode()).hexdigest()
    manifest = []
    for name in sources:
        if Path(name).name != name:
            raise ValueError("Nom de fichier source invalide")
        source = parser.SOURCE_DIR / name
        tickets, articles, rejects = parser.extract_workbook(source)
        if not tickets or not articles:
            raise ValueError(f"Aucun ticket ou article extrait de {name}")
        for kind, rows in zip(SCHEMAS, (tickets, articles, rejects)):
            target = output_dir / f"{kind}_{source.stem}.csv"
            parser.write_csv(rows, SCHEMAS[kind], target)
            manifest.append({"path": str(target), "kind": kind, "rows": len(rows)})
        logging.info(
            "%s : %s tickets, %s articles, %s anomalies ; sortie %s",
            name, len(tickets), len(articles), len(rejects), output_dir,
        )
    return manifest


def validate_outputs(manifest):
    if not manifest:
        raise ValueError("Aucun CSV produit")
    totals = dict.fromkeys(SCHEMAS, 0)
    for entry in manifest:
        with Path(entry["path"]).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != SCHEMAS[entry["kind"]]:
                raise ValueError(f"Schema CSV invalide : {entry['path']}")
            count = 0
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Ligne CSV mal formee : {entry['path']}")
                count += 1
        if count != entry["rows"]:
            raise ValueError(f"Nombre de lignes incorrect : {entry['path']}")
        totals[entry["kind"]] += count
    logging.info("CSV valides : %s", totals)
    if totals["rejects"]:
        logging.warning(
            "%s anomalies metier a examiner dans les fichiers rejects ; "
            "elles ne bloquent pas l'export, comme dans le parseur existant.",
            totals["rejects"],
        )
    return totals
