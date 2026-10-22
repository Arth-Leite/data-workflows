import json
from pathlib import Path

import numpy as np

from .. import registry

DRAWS = 1000
REQUIRED_WIN_RATE = 0.95


def paired_win_rate(
    challenger_sq: list[float],
    champion_sq: list[float],
    draws: int = DRAWS,
    seed: int = 0,
) -> float:
    challenger = np.asarray(challenger_sq, dtype=float)
    champion = np.asarray(champion_sq, dtype=float)
    if len(challenger) != len(champion) or len(challenger) == 0:
        raise ValueError("both models need the same non-empty test rows")
    picked = np.random.default_rng(seed).integers(0, len(challenger), size=(draws, len(challenger)))
    return float(np.mean(challenger[picked].mean(axis=1) < champion[picked].mean(axis=1)))


def main(metrics_path: str, models_dir: Path = registry.MODELS_DIR) -> str:
    metrics = json.loads(Path(metrics_path).read_text())
    challenger = metrics["challenger"]
    champion = metrics["champion"]
    rate = paired_win_rate(challenger["squared_errors"], champion["squared_errors"])
    reason = (
        f"challenger {metrics['model']} RMSE {challenger['rmse']:.2f}"
        f" vs {champion['artifact']} RMSE {champion['rmse']:.2f}"
        f", paired win rate {rate:.0%} over {DRAWS} draws"
    )
    passed = rate >= REQUIRED_WIN_RATE
    print(f"{'promote' if passed else 'reject'}: {reason}")
    if passed:
        return "promote"
    registry.append_history(
        metrics,
        "rejected",
        passed=False,
        reasons=reason,
        active=(registry.read_active(models_dir) or {}).get("run"),
        models_dir=models_dir,
    )
    return "reject"
