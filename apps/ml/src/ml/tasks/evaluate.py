import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from .. import registry
from ..features import (
    TARGET,
    coefficients_of,
    config_of,
    features_of,
    non_negative,
)


def scores(model, df: pd.DataFrame) -> dict:
    # /predict floors at zero, so a model is scored on what it would serve.
    predictions = non_negative(model.predict(df))
    squared_errors = (df[TARGET].to_numpy(dtype=float) - predictions) ** 2
    return {
        "test_length": len(df),
        "rmse": float(root_mean_squared_error(df[TARGET], predictions)),
        "mae": float(mean_absolute_error(df[TARGET], predictions)),
        "squared_errors": squared_errors.tolist(),
    }


def baseline_scores(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    baseline = DummyRegressor(strategy="mean").fit(train, train[TARGET])
    return {"artifact": "mean-baseline", **scores(baseline, test)}


def champion_scores(train: pd.DataFrame, test: pd.DataFrame, models_dir: Path) -> dict:
    if registry.read_active(models_dir) is None:
        return baseline_scores(train, test)
    active, model = registry.active_model(models_dir)
    return {
        "artifact": active["artifact"],
        **scores(model, test),
    }


def evaluate(
    model,
    train: pd.DataFrame,
    test: pd.DataFrame,
    run: str,
    models_dir: Path,
) -> dict:
    return {
        "run": run,
        "model": config_of(model),
        "algorithm": type(model[-1]).__name__,
        "features": features_of(model),
        "challenger": scores(model, test),
        "champion": champion_scores(train, test, models_dir),
        "coefficients": coefficients_of(model) if hasattr(model[-1], "coef_") else {},
        "intercept": getattr(model[-1], "intercept_", None),
        "train_length": len(train),
    }


def main(
    train_path: str,
    test_path: str,
    model_path: str,
    metrics_path: str,
    run: str | None = None,
    models_dir: Path = registry.MODELS_DIR,
    split_path: str | None = None,
) -> dict:
    df_train = pd.read_csv(train_path)
    df_test = pd.read_csv(test_path)
    metrics = evaluate(
        joblib.load(model_path),
        df_train,
        df_test,
        run or registry.utc_stamp(registry.RUN_ID_FORMAT),
        Path(models_dir),
    )

    # The scores are only readable next to the rows they were measured on.
    if split_path and Path(split_path).exists():
        metrics["split"] = json.loads(Path(split_path).read_text())

    Path(metrics_path).write_text(json.dumps(metrics, indent=2))

    challenger, champion = metrics["challenger"], metrics["champion"]
    print(f"challenger RMSE {challenger['rmse']:.2f}  MAE {challenger['mae']:.2f}")
    print(f"champion  RMSE {champion['rmse']:.2f}  MAE {champion['mae']:.2f}  ({champion['artifact']})")
    coefs = " ".join(f"{v:+.2f}*{k}" for k, v in metrics["coefficients"].items())
    print(f"fit {TARGET} = {metrics['intercept']} {coefs} on {metrics['features']}")
    print(f"run {metrics['run']} -> {metrics_path}")
    return metrics
