import json
import shutil
from pathlib import Path

from .. import registry


def main(model_path: str, metrics_path: str, models_dir: Path = registry.MODELS_DIR) -> None:
    metrics = json.loads(Path(metrics_path).read_text())
    artifact = Path(models_dir) / metrics["run"]
    if artifact.exists():
        raise FileExistsError(f"{artifact} already exists: run ids are unique")
    artifact.mkdir(parents=True)

    shutil.copy2(model_path, artifact / "model.joblib")
    shutil.copy2(metrics_path, artifact / "metrics.json")
    print(f"registered {metrics['run']} ({metrics['model']}) in {artifact}")
