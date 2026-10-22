"""One pipeline stage per module."""

from . import (
    combine_datasets,
    evaluate,
    gate,
    ingest_and_validate,
    promote,
    register,
    split_train_test,
    train,
)

__all__ = [
    "combine_datasets",
    "evaluate",
    "gate",
    "ingest_and_validate",
    "promote",
    "register",
    "split_train_test",
    "train",
]
