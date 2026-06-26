import json
import os
import random

import duckdb
from dagster import Config, job, op
from faker import Faker

os.makedirs("./task-outputs", exist_ok=True)


class GenerateConfig(Config):
    output_filepath: str = "./task-outputs/fake_employee_data.json"
    num_rows: int = 100


class MetricsConfig(Config):
    output_filepath: str = "./task-outputs/metrics.csv"


@op
def generate_data(config: GenerateConfig) -> str:
    fake = Faker()
    positions = ["Admin", "Manager", "Department Head", "Engineer", "Analyst"]
    data = [
        {
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "position": random.choice(positions),
            "salary": round(random.uniform(40000, 180000), 2),
            "sex": random.choice(["Male", "Female"]),
        }
        for _ in range(config.num_rows)
    ]
    with open(config.output_filepath, "w") as f:
        json.dump(data, f)

    return config.output_filepath


@op
def calculate_salary_metrics(
    context, input_filepath: str, config: MetricsConfig
) -> None:
    result = duckdb.sql(
        f"SELECT position, sex, AVG(salary) as average_salary "
        f"FROM read_json_auto('{input_filepath}') "
        f"GROUP BY position, sex "
        f"ORDER BY position, sex"
    )
    result.write_csv(config.output_filepath)
    context.log.info(f"Metrics written to {config.output_filepath}")


@job
def data_processing_job():
    calculate_salary_metrics(generate_data())
