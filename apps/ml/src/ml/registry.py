import csv
import json
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path

import joblib

APP_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(os.environ.get("ML_MODELS_DIR", APP_ROOT / "models"))
LOGS_DIR = Path(os.environ.get("ML_LOGS_DIR", APP_ROOT / "logs"))

RUN_ID_FORMAT = "%Y-%m-%dT%H-%M-%SZ"
HISTORY_COLUMNS = [
    "timestamp",
    "run",
    "status",
    "model",
    "challenger_rmse",
    "challenger_mae",
    "champion_rmse",
    "improvement_vs_champion_pct",
    "gate_passed",
    "gate_reasons",
    "active_model",
]


def utc_stamp(fmt: str = "%Y-%m-%dT%H:%M:%S+00:00") -> str:
    return datetime.now(UTC).strftime(fmt)


def save_model(model, path: Path) -> None:
    """Stdlib pickle: joblib would use dill when Airflow imports it first."""
    with Path(path).open("wb") as file:
        pickle.dump(model, file, protocol=pickle.HIGHEST_PROTOCOL)


def read_active(models_dir: Path = MODELS_DIR) -> dict | None:
    path = Path(models_dir) / "active.json"
    return json.loads(path.read_text()) if path.exists() else None


def write_active(entry: dict, models_dir: Path = MODELS_DIR) -> Path:
    """Swap the pointer atomically, so a reader never sees a half-written file."""
    path = Path(models_dir) / "active.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(entry, indent=2))
    os.replace(temporary, path)
    return path


def active_model(models_dir: Path = MODELS_DIR) -> tuple[dict, object]:
    """The active entry, and the model it names."""
    active = read_active(models_dir)
    if active is None:
        raise FileNotFoundError(f"{Path(models_dir) / 'active.json'} does not exist: nothing is promoted")
    path = Path(models_dir) / active["artifact"] / "model.joblib"
    if not path.exists():
        raise FileNotFoundError(f"active.json points at {path}, which does not exist")
    return active, joblib.load(path)


def active_entry(metrics: dict) -> dict:
    """The pointer for a promoted run: which artifact serves, and what it scored."""
    return {
        "run": metrics["run"],
        "artifact": metrics["run"],
        "model": metrics["model"],
        "algorithm": metrics["algorithm"],
        "features": metrics["features"],
        "promoted_at": utc_stamp(),
        # Per-row errors stay in metrics.json; the pointer keeps the summary.
        "metrics": {key: value for key, value in metrics["challenger"].items() if key != "squared_errors"},
    }


def append_history(
    metrics: dict,
    status: str,
    *,
    passed: bool | None = None,
    reasons: str = "",
    active: str | None = None,
    models_dir: Path = MODELS_DIR,
) -> Path:
    """Append one row of run history, whatever the run's outcome."""
    challenger = metrics["challenger"]
    # Champion #0 was never compared to anything, so it has no champion to report.
    champion_rmse = (metrics["champion"] or {}).get("rmse")
    row = {
        "timestamp": utc_stamp(),
        "run": metrics["run"],
        "status": status,
        "model": metrics["model"],
        "challenger_rmse": round(challenger["rmse"], 4),
        "challenger_mae": round(challenger["mae"], 4),
        "champion_rmse": round(champion_rmse, 4) if champion_rmse else "",
        "improvement_vs_champion_pct": (
            round(100 * (1 - challenger["rmse"] / champion_rmse), 2) if champion_rmse else ""
        ),
        "gate_passed": passed,
        "gate_reasons": reasons,
        "active_model": active,
    }

    path = Path(models_dir) / "metrics_history.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text().splitlines()[:1] != [",".join(HISTORY_COLUMNS)]:
        path.rename(path.with_name("metrics_history.legacy.csv"))
    new_file = not path.exists()
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    return path
