import argparse

from airflow_pipelines.tasks.employee_data import calculate_salary_metrics_duckdb, generate_and_save_data

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
