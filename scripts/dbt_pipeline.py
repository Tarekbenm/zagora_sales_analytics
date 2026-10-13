"""Executer dbt Core apres le chargement, avec la connexion stockee dans Airflow."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from databricks_loader import SqlClient, identifier


DBT_EXECUTABLE = Path("/home/airflow/dbt-venv/bin/dbt")
PROJECT_SOURCE = Path("/opt/airflow/dbt_source")
ARTIFACT_ROOT = Path("/opt/airflow/logs/dbt")
TOKEN_ENV = "DBT_ENV_SECRET_DATABRICKS_TOKEN"


def make_profile(connection):
    # Reutiliser la validation du hostname, du warehouse et du catalogue.
    SqlClient(connection)
    extra = connection.extra_dejson
    schema = extra.get("dbt_schema", "dbt_boucherie_dev")
    identifier(schema)
    if schema == extra.get("schema", "boucherie_raw"):
        raise ValueError("Le schema dbt doit etre distinct du schema source.")
    return {"boucherie": {
        "target": "airflow",
        "outputs": {"airflow": {
            "type": "databricks",
            "host": connection.host.strip().removeprefix("https://").rstrip("/"),
            "http_path": extra["http_path"],
            "catalog": extra.get("catalog", "workspace"),
            "schema": schema,
            "token": "{{ env_var('DBT_ENV_SECRET_DATABRICKS_TOKEN') }}",
            "threads": 1,
        }},
    }}


def execute_build(connection, run_id, source=PROJECT_SOURCE, executable=DBT_EXECUTABLE, artifact_root=ARTIFACT_ROOT):
    profile = make_profile(connection)
    if not Path(executable).is_file():
        raise FileNotFoundError("dbt absent du conteneur. Reconstruire l'image puis recreer le worker Docker.")
    if not (Path(source) / "dbt_project.yml").is_file():
        raise FileNotFoundError("Projet dbt absent. Reappliquer docker compose up -d pour monter les fichiers.")

    folder = Path(artifact_root) / hashlib.sha256(run_id.encode()).hexdigest() / uuid.uuid4().hex
    project = folder / "project"
    project.mkdir(parents=True)
    shutil.copy2(Path(source) / "dbt_project.yml", project / "dbt_project.yml")
    for name in ("models", "seeds", "tests", "macros"):
        directory = Path(source) / name
        if directory.is_dir():
            shutil.copytree(directory, project / name)
    # Snapshot par tentative : dbt ne modifie pas le depot monte en lecture seule.
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update({
        TOKEN_ENV: connection.password,
        "PYTHONNOUSERSITE": "1",
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        "DBT_USE_COLORS": "false",
    })
    with tempfile.TemporaryDirectory(prefix="boucherie_dbt_profile_") as profiles:
        # JSON est une syntaxe YAML valide ; le profil ne contient pas le token.
        profile_path = Path(profiles) / "profiles.yml"
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        profile_path.chmod(0o600)
        command = [
            str(executable), "build", "--project-dir", str(project),
            "--profiles-dir", profiles, "--target", "airflow",
            "--target-path", str(folder / "target"), "--log-path", str(folder / "logs"),
        ]
        logging.info("dbt build commence ; artefacts : %s", folder)
        try:
            result = subprocess.run(
                command, cwd=project, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", timeout=6600, check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("dbt a depasse 110 minutes. Verifier les requetes Databricks et les journaux dbt.") from None
        # dbt masque les variables DBT_ENV_SECRET ; protection supplementaire ici.
        logging.info("Sortie dbt :\n%s", result.stdout.replace(connection.password, "***"))
        if result.returncode != 0:
            raise RuntimeError(f"dbt build a echoue (code {result.returncode}). Voir les erreurs ci-dessus et {folder / 'logs'}.")

    result_path = folder / "target" / "run_results.json"
    if not result_path.is_file():
        raise RuntimeError("dbt termine sans run_results.json : resultat non verifiable.")
    results = json.loads(result_path.read_text(encoding="utf-8")).get("results", [])
    if not results or any(item.get("status") not in ("success", "pass", "warn") for item in results):
        raise RuntimeError("dbt contient des ressources en echec ou ignorees. Consulter run_results.json.")
    logging.info("dbt build termine : %s ressources ; artefacts : %s", len(results), folder)
    return {"resources": len(results), "artifacts": str(folder)}


def build_dbt(run_id):
    from airflow.hooks.base import BaseHook

    return execute_build(BaseHook.get_connection("databricks_boucherie"), run_id)
