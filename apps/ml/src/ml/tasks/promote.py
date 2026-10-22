import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import joblib

from .. import registry


def serving_url() -> str:
    return os.environ.get("SERVING_URL", "http://localhost:8000")


def reload_serving(url: str | None = None) -> str:
    call = urllib.request.Request((url or serving_url()).rstrip("/") + "/reload", method="POST")
    try:
        with urllib.request.urlopen(call, timeout=5) as response:
            return json.load(response)["run"]
    except (urllib.error.URLError, OSError) as error:
        return f"{error} (the pointer moved; a restart serves it)"


def main(run: str, models_dir: Path = registry.MODELS_DIR) -> None:
    artifact = Path(models_dir) / run
    joblib.load(artifact / "model.joblib")  # fail before the pointer moves
    metrics = json.loads((artifact / "metrics.json").read_text())

    registry.write_active(registry.active_entry(metrics), models_dir)
    registry.append_history(
        metrics,
        "promoted",
        passed=True,
        active=(registry.read_active(models_dir) or {}).get("run"),
        models_dir=models_dir,
    )
    print(f"serving {metrics['model']} {run} RMSE {metrics['challenger']['rmse']:.2f}")
    print(f"reload {serving_url()} -> {reload_serving()}")
