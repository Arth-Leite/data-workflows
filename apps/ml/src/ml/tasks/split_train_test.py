import json
from pathlib import Path
from zlib import crc32

import pandas as pd

from ..features import TARGET

TEST_SIZE = 0.2

TARGET_BIN_EDGES = [-0.1, 2, 5, 9, 13, float("inf")]
TARGET_BIN_LABELS = ["0-2", "3-5", "6-9", "10-13", "14+"]


def hash_fraction(vehicle_id: int, split_salt: str) -> float:
    """Deterministic draw in [0, 1) for a vehicle: the side it falls on."""
    return crc32(f"{split_salt}:{vehicle_id}".encode()) / 2**32


def target_distribution_by_bin(df: pd.DataFrame, is_test: pd.Series) -> pd.DataFrame:
    """Row count and target-bin shares of the full data, the train set and the test set."""
    bins = pd.cut(df[TARGET], TARGET_BIN_EDGES, labels=TARGET_BIN_LABELS)
    subsets = {"full": bins, "train": bins[~is_test], "test": bins[is_test]}
    shares = {f"{name}_share": bins_.value_counts(normalize=True).round(3) for name, bins_ in subsets.items()}
    return pd.DataFrame({"rows": bins.value_counts(), **shares}).loc[TARGET_BIN_LABELS]


def main(
    frame_path: str,
    train_path: str,
    test_path: str,
    split_path: str,
    test_size: float = TEST_SIZE,
    split_salt: str = "v1",
) -> None:
    df = pd.read_csv(frame_path)
    is_test = df["vehicle_id"].map(lambda v: hash_fraction(v, split_salt)) < test_size
    df_train, df_test = df[~is_test], df[is_test]

    df_train.to_csv(train_path, index=False)
    df_test.to_csv(test_path, index=False)

    distribution = target_distribution_by_bin(df, is_test)
    record = {
        "test_size": test_size,
        "split_salt": split_salt,
        "rows": {"full": len(df), "train": len(df_train), "test": len(df_test)},
        "target_share_by_bin": {
            str(bin_): {column: int(value) if column == "rows" else float(value) for column, value in row.items()}
            for bin_, row in distribution.iterrows()
        },
    }
    Path(split_path).write_text(json.dumps(record, indent=2))

    print(f"train rows: {len(df_train)} -> {train_path}")
    print(f"test rows: {len(df_test)} -> {test_path}")
    print(f"target share by bin, train and test against the full data ({split_path}):")
    print(distribution.to_string())
