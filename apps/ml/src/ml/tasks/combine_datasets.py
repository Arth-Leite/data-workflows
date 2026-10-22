import pandas as pd


def main(vehicles_path: str, reservations_path: str, output_path: str) -> None:
    vehicles_df = pd.read_csv(vehicles_path)
    reservations_df = pd.read_csv(reservations_path)

    df = vehicles_df.merge(
        reservations_df["vehicle_id"].value_counts().to_frame(),
        on="vehicle_id",
        how="left",
    ).rename(columns={"count": "n_reservations"})

    df["n_reservations"] = df["n_reservations"].fillna(0).astype(int)

    df.to_csv(output_path, index=False)
