FROM apache/airflow:2.9.2
RUN pip install --no-cache-dir "apache-airflow==2.9.2" "openpyxl==3.1.5"

# dbt a ses propres dependances, sans modifier celles d'Airflow.
RUN python -m venv /home/airflow/dbt-venv
COPY requirements-dbt.txt /tmp/requirements-dbt.txt
RUN --mount=type=cache,target=/home/airflow/.cache/pip,uid=50000,gid=0 \
    PIP_USER=false /home/airflow/dbt-venv/bin/pip install --timeout 120 --retries 10 -r /tmp/requirements-dbt.txt \
    && /home/airflow/dbt-venv/bin/pip check
