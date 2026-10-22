import json
import logging
import threading
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from time import perf_counter

import pandas as pd
from fastapi import FastAPI, HTTPException
from pandera.errors import SchemaError, SchemaErrors
from pydantic import BaseModel

from ml import registry
from ml.data_contracts import request_schema
from ml.features import non_negative

logger = logging.getLogger("serving")

# One worker, but sync endpoints run in a thread pool: two reloads at once
# would race on app.state. The lock is what makes the swap a swap.
reload_lock = threading.Lock()


class PredictionRequest(BaseModel):
    actual_price: float
    recommended_price: float
    num_images: int | None = None
    technology: int | None = None
    description: int | None = None
    street_parked: int | None = None


class PredictionResponse(BaseModel):
    prediction: float
    run: str
    features: list[str]


def log_prediction(prediction: dict) -> None:
    registry.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = registry.LOGS_DIR / f"predictions-{date.today():%Y-%m-%d}.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps(prediction) + "\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.active, app.state.model = registry.active_model(registry.MODELS_DIR)
        logger.info("serving %s on %s", app.state.active["run"], app.state.active["features"])
    except FileNotFoundError as error:
        app.state.active, app.state.model = None, None
        logger.warning("starting without a model: %s", error)
    yield


app = FastAPI(title="reservations", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok" if app.state.model else "degraded",
        "run": app.state.active["run"] if app.state.active else None,
        "features": app.state.active["features"] if app.state.active else [],
    }


@app.post("/reload")
def reload_model() -> dict:
    """Serve whatever ``active.json`` names now.

    Promotion happens in the pipeline, in another container: without this the
    api keeps serving the model it loaded at startup until it is restarted.
    """
    with reload_lock:
        try:
            active, model = registry.active_model(registry.MODELS_DIR)
        except (OSError, KeyError) as error:
            raise HTTPException(503, str(error)) from error
        previous = app.state.active["run"] if app.state.active else None
        if active["run"] != previous:
            logger.info("reloading %s -> %s", previous, active["run"])
        app.state.active, app.state.model = active, model
    return {"run": active["run"], "features": active["features"]}


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest) -> PredictionResponse:
    started = perf_counter()

    if app.state.model is None:
        raise HTTPException(503, "no model is promoted yet")

    # Validates the data-contract and enforces schema
    try:
        df = request_schema.validate(pd.DataFrame([payload.model_dump()]))
    except (SchemaError, SchemaErrors) as error:
        raise HTTPException(422, str(error)) from error

    raw_prediction = float(app.state.model.predict(df)[0])
    non_neg_prediction = float(non_negative(raw_prediction))

    log_prediction(
        {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "run": app.state.active["run"],
            **payload.model_dump(),
            "raw_prediction": raw_prediction,
            "prediction": non_neg_prediction,
            "latency_ms": round(1000 * (perf_counter() - started), 2),
        }
    )
    return PredictionResponse(
        prediction=non_neg_prediction,
        run=app.state.active["run"],
        features=app.state.active["features"],
    )
