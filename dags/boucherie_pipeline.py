"""Excel -> CSV controles -> Databricks -> dbt build."""

from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


@dag(
    dag_id="boucherie_pipeline",
    description="Excel, controle CSV, chargement Databricks et construction/tests dbt",
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Paris"),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["boucherie", "jedha"],
)
def boucherie_pipeline():
    @task
    def verifier_sources():
        from airflow_pipeline import check_sources

        return check_sources()

    @task(execution_timeout=timedelta(minutes=30))
    def parser_excel(sources):
        from airflow_pipeline import normalize_sources

        return normalize_sources(sources, get_current_context()["run_id"])

    @task
    def controler_csv(manifest):
        from airflow_pipeline import validate_outputs

        return validate_outputs(manifest)

    @task(execution_timeout=timedelta(hours=2), retries=0)
    def charger_databricks(manifest):
        from databricks_loader import load_databricks

        return load_databricks(manifest)

    @task(execution_timeout=timedelta(hours=2), retries=0)
    def dbt_build():
        from dbt_pipeline import build_dbt

        return build_dbt(get_current_context()["run_id"])

    manifest = parser_excel(verifier_sources())
    validation = controler_csv(manifest)
    chargement = charger_databricks(manifest)
    validation >> chargement
    chargement >> dbt_build()


boucherie_pipeline()
