import csv
import random

import duckdb
from faker import Faker

POSITIONS = ["Admin", "Manager", "Department Head", "Engineer", "Analyst"]


def generate_and_save_data(output_filepath: str) -> None:
    """Generates fake data and saves it to a CSV file."""
    fake = Faker()
    num_records = 1000
    data = []

    print(f"Generating {num_records} fake employee records...")
    for _ in range(num_records):
        data.append(
            {
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "position": random.choice(POSITIONS),
                "salary": round(random.uniform(40000, 180000), 2),
                "sex": random.choice(["Male", "Female"]),
            }
        )

    print(f"Saving data to {output_filepath}")
    with open(output_filepath, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    print("Data generation complete.")


def calculate_salary_metrics_duckdb(input_filepath: str, output_filepath: str) -> None:
    """Calculates salary metrics by position and sex."""
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
        raise

    print(f"Saving metrics to {output_filepath}")
    avg_salary_by_position_sex.write_csv(output_filepath)
    print("Metrics calculation complete.")
