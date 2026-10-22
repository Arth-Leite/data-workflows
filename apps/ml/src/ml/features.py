from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import FunctionTransformer

TARGET = "n_reservations"


def non_negative(predictions):
    """What serving returns: a reservation count cannot be negative."""
    return np.maximum(predictions, 0.0)


MODEL_CONFIGS = {
    "linear-full": {
        "columns": ["price_ratio", "num_images", "technology"],
        "estimator": LinearRegression(),
    },
    # example where we would have another model
    "linear-price": {
        "columns": ["price_ratio"],
        "estimator": LinearRegression(),
    },
}
DEFAULT_MODEL = "linear-full"


def with_price_ratio(X):
    return X.assign(price_ratio=X["actual_price"] / X["recommended_price"])


class ClipToRange(BaseEstimator, TransformerMixin):
    """A column, bounded to the range the training rows showed."""

    def __init__(self, lower_quantile: float = 0.0, upper_quantile: float = 1.0):
        self.lower_quantile = lower_quantile
        self.upper_quantile = upper_quantile

    def fit(self, X, y=None):
        values = np.asarray(X, dtype=float).ravel()
        self.lower_ = float(np.nanquantile(values, self.lower_quantile))
        self.upper_ = float(np.nanquantile(values, self.upper_quantile))
        return self

    def transform(self, X):
        return np.clip(np.asarray(X, dtype=float), self.lower_, self.upper_)


def prepare(column: str):
    """What happens to one input column before the estimator sees it."""
    if column == "price_ratio":
        return ClipToRange()
    if column == "num_images":
        return make_pipeline(
            SimpleImputer(strategy="constant", fill_value=1),
            ClipToRange(),
        )
    if column == "technology":
        return SimpleImputer(strategy="constant", fill_value=0)
    return "passthrough"


def make_model(model: str, estimator=None) -> Pipeline:
    config = MODEL_CONFIGS[model]

    if estimator is None:
        estimator = config["estimator"]

    pipeline = make_pipeline(
        FunctionTransformer(with_price_ratio),
        ColumnTransformer([(c, prepare(c), [c]) for c in config["columns"]]),
        clone(estimator),
    )

    pipeline.model_config = model
    return pipeline


def features_of(model: Pipeline) -> list[str]:
    return [column for _, _, columns in model[1].transformers for column in columns]


def config_of(model: Pipeline) -> str:
    return getattr(model, "model_config", DEFAULT_MODEL)


def coefficients_of(model: Pipeline) -> dict[str, float]:
    return dict(zip(features_of(model), map(float, model[-1].coef_)))
