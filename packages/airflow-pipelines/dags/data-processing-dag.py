from __future__ import annotations

import csv
import datetime
import os
import random

import duckdb
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from faker import Faker

# Define file paths
BASE_DIR = "/opt/airflow/"  # Root for data and DAGs
DATA_DIR = os.path.join(BASE_DIR, "task-outputs")
RAW_DATA_FILE = os.path.join(DATA_DIR, "fake_employee_data.json")
METRICS_FILE = os.path.join(DATA_DIR, "salary_metrics.csv")

os.makedirs(DATA_DIR, exist_ok=True)  # exist_ok avoids the if-check


def _generate_and_save_data(**context):
    """Generates fake data and saves it to a CSV file."""
    fake = Faker()
    num_records = 1000
    data = []
    positions = ["Admin", "Manager", "Department Head", "Engineer", "Analyst"]

    print(f"Generating {num_records} fake employee records...")
    for _ in range(num_records):
        data.append(
            {
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "position": random.choice(positions),
                "salary": round(random.uniform(40000, 180000), 2),
                "sex": random.choice(["Male", "Female"]),
            }
        )

    output_filepath = context["params"]["output_filepath"]
    print(f"Saving data to {output_filepath}")

    with open(output_filepath, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    print("Data generation complete.")


# def _calculate_salary_metrics_polars(**context):
#     """Calculates salary metrics by position and sex."""
#     input_filepath = context["params"]["input_filepath"]
#     output_filepath = context["params"]["output_filepath"]
#
#     print(f"Reading data from {input_filepath}")
#     try:
#         df = pl.scan_csv(input_filepath)
#     except FileNotFoundError:
#         print(f"Error: Input file not found at {input_filepath}")
#         raise  # Raise the exception to fail the task
#
#     print(df.collect_schema())
#     print("Calculating salary metrics by position and sex...")
#
#     # Calculate average salary by position and sex
#     avg_salary_by_position_sex = (
#         df.group_by(["position", "sex"])
#         .agg(pl.mean("salary").alias("average_salary"))
#         .sort(["position", "sex"])
#     )
#
#     print(f"Saving metrics to {output_filepath}")
#     avg_salary_by_position_sex.sink_csv(output_filepath)
#     print("Metrics calculation complete.")


def _calculate_salary_metrics_duckdb(**context):
    """Calculates salary metrics by position and sex."""
    input_filepath = context["params"]["input_filepath"]
    output_filepath = context["params"]["output_filepath"]

    print(f"Reading data from {input_filepath}")
    try:
        avg_salary_by_position_sex = duckdb.sql(
            f"SELECT position, sex, AVG(salary) as average_salary "
            f"FROM '{input_filepath}' "
            "GROUP BY position, sex "
            "ORDER BY position, sex"
        )
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_filepath}")
        raise  # Raise the exception to fail the task

    print(f"Saving metrics to {output_filepath}")
    avg_salary_by_position_sex.write_csv(output_filepath)
    print("Metrics calculation complete.")


with DAG(
    dag_id="data_processing_pipeline",
    start_date=datetime.datetime(2023, 10, 26),
    schedule="@daily",
    catchup=False,
    tags=["data-processing", "fake-data", "metrics"],
    # Define default params that can be overridden by tasks
    params={
        "output_filepath": RAW_DATA_FILE,
        "input_filepath": RAW_DATA_FILE,
        "output_filepath_metrics": METRICS_FILE,
    },
) as dag:
    generate_data_task = PythonOperator(
        task_id="generate_fake_employee_data",
        python_callable=_generate_and_save_data,
        params={"output_filepath": RAW_DATA_FILE},
    )

    # polars_calculate_metrics_task = PythonOperator(
    #     task_id="calculate_salary_metrics",
    #     python_callable=_calculate_salary_metrics_polars,
    #     params={
    #         "input_filepath": RAW_DATA_FILE,
    #         "output_filepath": METRICS_FILE,
    #     },
    # )

    duckdb_calculate_metrics_task = PythonOperator(
        task_id="calculate_salary_metrics",
        python_callable=_calculate_salary_metrics_duckdb,
        params={
            "input_filepath": RAW_DATA_FILE,
            "output_filepath": METRICS_FILE,
        },
    )

    generate_data_task >> duckdb_calculate_metrics_task
