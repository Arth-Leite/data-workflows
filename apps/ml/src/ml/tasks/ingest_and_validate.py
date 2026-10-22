import pandas as pd

from ..data_contracts import reservations_schema, vehicles_schema


def main(vehicles_path: str, reservations_path: str) -> None:
    vehicles_df = pd.read_csv(vehicles_path)
    reservations_df = pd.read_csv(reservations_path)

    vehicles_schema.validate(vehicles_df, lazy=True)
    reservations_schema.validate(reservations_df, lazy=True)

    unknown = set(reservations_df["vehicle_id"]) - set(vehicles_df["vehicle_id"])
    if unknown:
        raise ValueError(f"Unknown vehicle_id(s) in reservations: {sorted(unknown)}")
