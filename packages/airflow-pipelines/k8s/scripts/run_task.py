import argparse


def generate_and_save_data(output_filepath):
    """Generates fake data and saves it to a CSV file."""
    import csv
    import random

    from faker import Faker

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

    print(f"Saving data to {output_filepath}")

    with open(output_filepath, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

    print("Data generation complete.")


def calculate_salary_metrics_duckdb(input_filepath, output_filepath):
    """Calculates salary metrics by position and sex."""
    import duckdb

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    gen = subparsers.add_parser("generate-data")
    gen.add_argument("--output", required=True)

    calc = subparsers.add_parser("calculate-metrics")
    calc.add_argument("--input", required=True)
    calc.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "generate-data":
        generate_and_save_data(args.output)
    elif args.command == "calculate-metrics":
        calculate_salary_metrics_duckdb(args.input, args.output)
