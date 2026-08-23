from __future__ import annotations

import datetime
import os

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from airflow_pipelines.tasks.employee_data import calculate_salary_metrics_duckdb, generate_and_save_data

# Define file paths
BASE_DIR = "/opt/airflow/"  # Root for data and DAGs
DATA_DIR = os.path.join(BASE_DIR, "task-outputs")
RAW_DATA_FILE = os.path.join(DATA_DIR, "fake_employee_data.json")
METRICS_FILE = os.path.join(DATA_DIR, "salary_metrics.csv")

os.makedirs(DATA_DIR, exist_ok=True)  # exist_ok avoids the if-check

with DAG(
    dag_id="data_processing_pipeline",
    start_date=datetime.datetime(2023, 10, 26),
    schedule="@daily",
    catchup=False,
    tags=["data-processing", "fake-data", "metrics"],
) as dag:
    generate_data_task = PythonOperator(
        task_id="generate_fake_employee_data",
        python_callable=generate_and_save_data,
        op_kwargs={"output_filepath": RAW_DATA_FILE},
    )

    duckdb_calculate_metrics_task = PythonOperator(
        task_id="calculate_salary_metrics",
        python_callable=calculate_salary_metrics_duckdb,
        op_kwargs={"input_filepath": RAW_DATA_FILE, "output_filepath": METRICS_FILE},
    )

    generate_data_task >> duckdb_calculate_metrics_task
