"""The smallest set that catches a broken promote-then-serve loop."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from ml import data_contracts, features, registry, serving
from ml.tasks import (
    evaluate,
    gate,
    ingest_and_validate,
    promote,
    register,
    train,
)
from sklearn.dummy import DummyRegressor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dataset() -> pd.DataFrame:
    """The frame the stages hand a model: raw fields plus the label."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "actual_price": rng.uniform(50, 150, 60),
            "recommended_price": 100.0,
            "num_images": rng.integers(1, 10, 60),
            "technology": rng.integers(0, 2, 60),
            "description": rng.integers(0, 500, 60),
            "street_parked": rng.integers(0, 2, 60),
        }
    )
    # Driven by price and images, so a model that asks for both is genuinely
    # better than one that asks for the price alone.
    ratio = df["actual_price"] / df["recommended_price"]
    df["n_reservations"] = (8 - 6 * ratio + 0.2 * df["num_images"]).clip(0)
    return df


@pytest.fixture(autouse=True)
def offline_api(monkeypatch):
    """Promotion pings the api's /reload; the tests are not running one."""
    monkeypatch.setattr(promote, "reload_serving", lambda url=None: "not running")


def split(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return dataset[:45], dataset[45:]


def metrics(run: str, challenger_rmse: float, champion_rmse: float) -> dict:
    """Only the fields the gate and the registry read."""

    def score(rmse: float) -> dict:
        return {
            "rmse": rmse,
            "mae": rmse,
            "test_length": 15,
            "squared_errors": [rmse**2] * 15,
        }

    return {
        "run": run,
        "model": "linear-full",
        "algorithm": "LinearRegression",
        "features": ["price_ratio", "num_images", "technology"],
        "challenger": score(challenger_rmse),
        "champion": {**score(champion_rmse), "artifact": "champion-0"},
    }


def install_mean_champion(train: pd.DataFrame, test: pd.DataFrame, run: str, models_dir: Path) -> None:
    model = features.make_model(features.DEFAULT_MODEL, estimator=DummyRegressor(strategy="mean")).fit(
        train, train[features.TARGET]
    )
    artifact = models_dir / run
    artifact.mkdir(parents=True)
    registry.save_model(model, artifact / "model.joblib")
    run_metrics = {
        "run": run,
        "model": features.DEFAULT_MODEL,
        "algorithm": "DummyRegressor",
        "features": features.features_of(model),
        "challenger": evaluate.scores(model, test),
        "champion": None,
    }
    (artifact / "metrics.json").write_text(json.dumps(run_metrics))
    registry.write_active(registry.active_entry(run_metrics), models_dir)


def test_pointer_round_trip(tmp_path):
    assert registry.read_active(tmp_path) is None
    registry.write_active(metrics("r1", 1, 2), tmp_path)
    assert registry.read_active(tmp_path)["run"] == "r1"
    assert list(tmp_path.glob("*.tmp")) == []


def test_artifact_loads_where_dill_is_missing(tmp_path):
    """Airflow imports dill before joblib, which is how a dill dependency got
    into the artifacts and killed the serving container on startup."""
    pytest.importorskip("dill")
    artifact = tmp_path / "model.joblib"
    child = (
        "import dill, joblib  # the order apache-airflow imports them in\n"
        "from ml import registry\n"
        f"registry.save_model({{'k': slice(0, 1)}}, {str(artifact)!r})\n"
    )
    subprocess.run([sys.executable, "-c", child], check=True, cwd=ROOT, capture_output=True)
    assert b"dill" not in artifact.read_bytes()


def test_gate_rejects_a_lower_rmse_that_the_resample_does_not_support(tmp_path):
    """A few lucky rows can lower RMSE while most resamples still prefer the champion."""
    champion = [10.0] * 10
    # Mean squared error 9.6 against the champion's 10, so RMSE alone would promote.
    challenger = [0.0, 0.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0]
    assert np.mean(challenger) < np.mean(champion)
    assert gate.paired_win_rate(challenger, champion) < gate.REQUIRED_WIN_RATE

    body = metrics("lucky", 1, 2)
    body["challenger"]["squared_errors"] = challenger
    body["champion"]["squared_errors"] = champion
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(body))

    assert gate.main(str(metrics_path), tmp_path) == "reject"
    assert "paired win rate" in (tmp_path / "metrics_history.csv").read_text()


def test_gate_blocks_a_worse_challenger(tmp_path):
    registry.write_active(metrics("champion-0", 1, 1), tmp_path)
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics("worse", 3, 2)))

    assert gate.main(str(metrics_path), tmp_path) == "reject"

    assert registry.read_active(tmp_path)["run"] == "champion-0"
    history = (tmp_path / "metrics_history.csv").read_text()
    assert "rejected" in history and "linear-full" in history


def test_scores_floor_at_zero_like_serving():
    """A raw score below zero is served as zero, so it is scored as zero."""

    class Negative:
        def predict(self, df):
            return np.array([-2.0, 1.0])

    got = evaluate.scores(Negative(), pd.DataFrame({"n_reservations": [0.0, 1.0]}))
    assert (got["rmse"], got["mae"]) == (0.0, 0.0)


def test_first_model_is_promoted_against_the_mean_baseline(tmp_path, dataset):
    train_df, test_df = split(dataset)
    train_path, test_path = tmp_path / "train.csv", tmp_path / "test.csv"
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)
    model_path, metrics_path = tmp_path / "model.joblib", tmp_path / "metrics.json"

    train.main(str(train_path), str(model_path), features.DEFAULT_MODEL)
    run_metrics = evaluate.main(
        str(train_path),
        str(test_path),
        str(model_path),
        str(metrics_path),
        "first-run",
        tmp_path,
    )
    assert run_metrics["champion"]["artifact"] == "mean-baseline"
    assert run_metrics["challenger"]["rmse"] < run_metrics["champion"]["rmse"]

    register.main(str(model_path), str(metrics_path), tmp_path)
    assert gate.main(str(metrics_path), tmp_path) == "promote"
    promote.main("first-run", tmp_path)
    assert registry.read_active(tmp_path)["run"] == "first-run"


def test_a_weaker_model_challenger_is_rejected_by_the_stronger_champion(tmp_path, dataset):
    """The story the pipeline is built for: one pipeline, one set of rows, two
    models that ask for different columns, and a gate that decides between them.
    """
    train_df, test_df = split(dataset)
    train_path, test_path = tmp_path / "train.csv", tmp_path / "test.csv"
    train_df.to_csv(train_path, index=False)
    test_df.to_csv(test_path, index=False)

    def score(model: str, run: str) -> tuple[Path, Path]:
        """Fit a model config and measure it against the champion, as the DAG does."""
        model_path, metrics_path = tmp_path / f"{run}.joblib", tmp_path / f"{run}.json"
        train.main(str(train_path), str(model_path), model)
        evaluate.main(
            str(train_path),
            str(test_path),
            str(model_path),
            str(metrics_path),
            run,
            tmp_path,
        )
        return model_path, metrics_path

    def ship(model: str, run: str) -> None:
        """Score it, register it, and let the gate decide what happens to it."""
        model_path, metrics_path = score(model, run)
        register.main(str(model_path), str(metrics_path), tmp_path)
        if gate.main(str(metrics_path), tmp_path) == "promote":
            promote.main(run, tmp_path)

    ship("linear-price", "price-1")
    assert registry.read_active(tmp_path)["model"] == "linear-price"
    assert registry.read_active(tmp_path)["features"] == ["price_ratio"]

    ship("linear-full", "full-1")
    assert registry.read_active(tmp_path)["features"] == [
        "price_ratio",
        "num_images",
        "technology",
    ]

    # the weaker model again: a challenger the gate has to refuse
    model_path, metrics_path = score("linear-price", "price-2")
    scored = json.loads(metrics_path.read_text())
    assert scored["challenger"]["rmse"] > scored["champion"]["rmse"]
    register.main(str(model_path), str(metrics_path), tmp_path)
    assert gate.main(str(metrics_path), tmp_path) == "reject"

    # the pointer did not move, but the refused artifact is on disk to inspect
    assert registry.read_active(tmp_path)["run"] == "full-1"
    assert (tmp_path / "price-2" / "model.joblib").exists()
    history = (tmp_path / "metrics_history.csv").read_text()
    assert "linear-price" in history and "linear-full" in history


def test_promote_tells_the_api_to_reload(tmp_path, dataset, monkeypatch):
    """A promotion has to reach the running process, or a manual step is left over."""
    train_df, test_df = split(dataset)
    install_mean_champion(train_df, test_df, "champion-0", tmp_path)

    calls = []
    monkeypatch.setattr(promote, "reload_serving", lambda url=None: calls.append(url) or "ok")
    promote.main("champion-0", tmp_path)
    assert calls == [None]


def test_predict_serves_the_active_model(tmp_path, dataset, monkeypatch):
    train_df, test_df = split(dataset)
    install_mean_champion(train_df, test_df, "champion-0", tmp_path)
    # the app reads both per call, but registry.MODELS_DIR is what it reads
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(registry, "LOGS_DIR", tmp_path / "logs")

    with TestClient(serving.app) as client:
        health = client.get("/health").json()
        assert health == {
            "status": "ok",
            "run": "champion-0",
            "features": features.MODEL_CONFIGS[features.DEFAULT_MODEL]["columns"],
        }

        # champion #0 is the mean predictor, so any valid request returns that mean
        body = client.post("/predict", json={"actual_price": 90, "recommended_price": 100}).json()
        assert body["prediction"] == pytest.approx(train_df["n_reservations"].mean())
        assert body["run"] == "champion-0"

        failed = client.post("/predict", json={"actual_price": -1, "recommended_price": 100})
        assert failed.status_code == 422

        # 10x the recommended price is outside every training row, and it is still
        # served: rejecting it would fail ingest the day the listings move, and the
        # range is the model's clip's business, not the contract's
        extrapolated = client.post("/predict", json={"actual_price": 1000, "recommended_price": 100})
        assert extrapolated.status_code == 200

        # no model reads street_parked, but the value still reaches the log, so one
        # outside the definition is refused here instead of counted as drift later
        unread = client.post(
            "/predict",
            json={"actual_price": 90, "recommended_price": 100, "street_parked": 5},
        )
        assert unread.status_code == 422

    # both served requests landed in the log, the refused one did not
    [logged] = (tmp_path / "logs").glob("*.jsonl")
    rows = [json.loads(line) for line in logged.read_text().splitlines()]
    assert [row["run"] for row in rows] == ["champion-0", "champion-0"]


def test_images_beyond_the_training_range_do_not_extrapolate(dataset):
    """100 images must serve like the most images a training row had."""
    model = features.make_model("linear-full").fit(dataset, dataset["n_reservations"])
    listing = {
        "actual_price": 90.0,
        "recommended_price": 100.0,
        "technology": 0,
    }
    many = pd.DataFrame([{**listing, "num_images": 100}])
    most = pd.DataFrame([{**listing, "num_images": dataset["num_images"].max()}])
    assert model.predict(many)[0] == pytest.approx(model.predict(most)[0])


BASE_PAYLOAD = {"actual_price": 90, "recommended_price": 100}


@pytest.fixture
def linear_api(tmp_path, dataset, monkeypatch):
    """Serving backed by a fitted model, so clipping is observable."""
    run = "linear-0"
    model = features.make_model("linear-full").fit(dataset, dataset["n_reservations"])
    (tmp_path / run).mkdir()
    registry.save_model(model, tmp_path / run / "model.joblib")
    registry.write_active(
        {
            "run": run,
            "artifact": run,
            "model": "linear-full",
            "algorithm": "LinearRegression",
            "features": features.features_of(model),
        },
        tmp_path,
    )
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(registry, "LOGS_DIR", tmp_path / "logs")


@pytest.mark.parametrize(
    "field,value",
    [
        ("actual_price", 0),
        ("recommended_price", 0),
        ("num_images", 0),
        ("num_images", -10),
        ("technology", 2),
        ("street_parked", -1),
        ("description", -1),
    ],
)
def test_absurd_values_in_each_field_are_refused(field, value, linear_api):
    with TestClient(serving.app) as client:
        response = client.post("/predict", json={**BASE_PAYLOAD, field: value})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("actual_price", 10**9),
        ("recommended_price", 0.01),
        ("num_images", 10**6),
        ("description", 10**12),
        ("technology", 1),
        ("street_parked", 1),
    ],
)
def test_absurd_values_in_each_field_are_served_when_valid(field, value, linear_api):
    with TestClient(serving.app) as client:
        body = client.post("/predict", json={**BASE_PAYLOAD, field: value}).json()
    assert np.isfinite(body["prediction"])
    assert body["prediction"] >= 0


def test_absurd_values_do_not_extrapolate(linear_api, dataset):
    edges = {
        "num_images": int(dataset["num_images"].max()),
        "actual_price": 2 * BASE_PAYLOAD["recommended_price"],  # top of the ratio clip
    }
    with TestClient(serving.app) as client:
        for field, edge in edges.items():
            absurd = client.post("/predict", json={**BASE_PAYLOAD, field: 10**9})
            at_edge = client.post("/predict", json={**BASE_PAYLOAD, field: edge})
            assert absurd.json()["prediction"] == pytest.approx(at_edge.json()["prediction"])


def test_the_request_contract_mirrors_the_payload():
    """A field the payload carries and the contract does not is one nothing checks."""
    assert set(data_contracts.request_schema.columns) == set(serving.PredictionRequest.model_fields)


def test_the_pipeline_accepts_the_nulls_serving_accepts():
    listing = pd.DataFrame(
        {
            "vehicle_id": [1],
            "technology": [None],
            "actual_price": [100.0],
            "recommended_price": [100],
            "num_images": [None],
            "street_parked": [None],
            "description": [None],
        }
    )
    data_contracts.vehicles_schema.validate(listing)
    data_contracts.request_schema.validate(listing.drop(columns=["vehicle_id"]))


def test_ingest_rejects_a_reservation_without_a_vehicle(tmp_path):
    vehicles = pd.DataFrame(
        {
            "vehicle_id": [1],
            "technology": [0],
            "actual_price": [100.0],
            "recommended_price": [100],
            "num_images": [4],
            "street_parked": [0],
            "description": [10],
        }
    )
    reservations = pd.DataFrame({"vehicle_id": [1, 999], "created_at": ["2023-01-01 10:00:00"] * 2})
    vehicles_path, reservations_path = tmp_path / "v.csv", tmp_path / "r.csv"
    vehicles.to_csv(vehicles_path, index=False)
    reservations.to_csv(reservations_path, index=False)

    with pytest.raises(ValueError, match="Unknown vehicle_id"):
        ingest_and_validate.main(str(vehicles_path), str(reservations_path))


def test_the_contract_does_not_bound_the_price_ratio():
    """A ratio no training row showed is drift to monitor, not a bad row."""
    listings = pd.DataFrame(
        {
            "vehicle_id": [1, 2],
            "technology": [0, 1],
            "actual_price": [100.0, 900.0],  # the second is 9x its recommended price
            "recommended_price": [100, 100],
            "num_images": [4, 8],
            "street_parked": [0, 1],
            "description": [10, 20],
        }
    )
    data_contracts.vehicles_schema.validate(listings)
    data_contracts.request_schema.validate(listings.drop(columns=["vehicle_id"]))


def test_reload_picks_up_a_new_champion(tmp_path, dataset, monkeypatch):
    """A promotion lands in another process: the api has to be able to follow it."""
    train_df, test_df = split(dataset)
    install_mean_champion(train_df, test_df, "champion-0", tmp_path)
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(registry, "LOGS_DIR", tmp_path / "logs")

    with TestClient(serving.app) as client:
        assert client.get("/health").json()["run"] == "champion-0"

        # a newer artifact is promoted while the api is up
        (tmp_path / "active.json").unlink()
        install_mean_champion(train_df, test_df, "champion-1", tmp_path)

        # the running app still serves the model it loaded
        assert client.get("/health").json()["run"] == "champion-0"
        assert client.post("/reload").json()["run"] == "champion-1"
        assert client.get("/health").json()["run"] == "champion-1"


def test_api_starts_without_a_model_and_serves_after_reload(tmp_path, dataset, monkeypatch):
    """A fresh clone has no artifacts: the api has to wait for a promotion."""
    train_df, test_df = split(dataset)
    monkeypatch.setattr(registry, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(registry, "LOGS_DIR", tmp_path / "logs")

    with TestClient(serving.app) as client:
        assert client.get("/health").json() == {
            "status": "degraded",
            "run": None,
            "features": [],
        }
        payload = {"actual_price": 90, "recommended_price": 100}
        assert client.post("/predict", json=payload).status_code == 503
        assert client.post("/reload").status_code == 503

        install_mean_champion(train_df, test_df, "champion-0", tmp_path)
        assert client.post("/reload").json()["run"] == "champion-0"
        assert client.get("/health").json()["status"] == "ok"
        assert client.post("/predict", json=payload).status_code == 200
