"""Train and promote a vehicle reservation model."""

import logging
import os
from datetime import datetime
from pathlib import Path

from airflow.sdk import Param, dag, get_current_context, task
from ml import tasks
from ml.features import DEFAULT_MODEL, MODEL_CONFIGS

DATA_DIR = Path(os.environ.get("ML_DATA_DIR", "/opt/airflow/ml-data"))
MODELS_DIR = Path(os.environ.get("ML_MODELS_DIR", "/opt/airflow/ml-output/models"))
WORK_ROOT = Path(os.environ.get("ML_WORK_DIR", "/opt/airflow/ml-output/runs"))


def run_id() -> str:
    dag_run = get_current_context()["dag_run"]
    timestamp = dag_run.logical_date or dag_run.run_after
    return timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")


def work_dir() -> Path:
    work = WORK_ROOT / run_id()
    work.mkdir(parents=True, exist_ok=True)
    return work


def model_name() -> str:
    return get_current_context()["params"]["model"]


def alert(context: dict) -> None:
    logging.getLogger("airflow.task").error(
        "stage %s failed: %s", context["task_instance"].task_id, context["exception"]
    )


@dag(
    dag_id="vehicle_reservations_training",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "on_failure_callback": alert},
    params={
        "model": Param(
            DEFAULT_MODEL,
            enum=list(MODEL_CONFIGS),
            description="Model configuration to train",
        )
    },
    tags=["ml", "training"],
)
def vehicle_reservations_training():
    @task
    def ingest_and_validate() -> None:
        tasks.ingest_and_validate.main(
            str(DATA_DIR / "vehicles.csv"),
            str(DATA_DIR / "reservations.csv"),
        )

    @task
    def combine_datasets() -> None:
        tasks.combine_datasets.main(
            str(DATA_DIR / "vehicles.csv"),
            str(DATA_DIR / "reservations.csv"),
            str(work_dir() / "frame.csv"),
        )

    @task
    def split_train_test() -> None:
        work = work_dir()
        tasks.split_train_test.main(
            str(work / "frame.csv"),
            str(work / "train.csv"),
            str(work / "test.csv"),
            str(work / "split.json"),
        )

    @task
    def train() -> None:
        work = work_dir()
        tasks.train.main(
            str(work / "train.csv"),
            str(work / "model.joblib"),
            model_name(),
        )

    @task
    def evaluate() -> None:
        work = work_dir()
        tasks.evaluate.main(
            str(work / "train.csv"),
            str(work / "test.csv"),
            str(work / "model.joblib"),
            str(work / "metrics.json"),
            run=run_id(),
            models_dir=MODELS_DIR,
            split_path=str(work / "split.json"),
        )

    @task
    def register() -> None:
        work = work_dir()
        tasks.register.main(
            str(work / "model.joblib"),
            str(work / "metrics.json"),
            MODELS_DIR,
        )

    @task.branch
    def gate() -> str:
        return tasks.gate.main(str(work_dir() / "metrics.json"), MODELS_DIR)

    @task(task_id="promote")
    def promote_run() -> None:
        tasks.promote.main(run_id(), MODELS_DIR)

    @task(task_id="reject")
    def reject_run() -> None:
        return None

    (
        ingest_and_validate()
        >> combine_datasets()
        >> split_train_test()
        >> train()
        >> evaluate()
        >> register()
        >> gate()
        >> [promote_run(), reject_run()]
    )


vehicle_reservations_training()
