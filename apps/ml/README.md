# ml

Vehicle reservation forecasting as an end-to-end ML package: data validation,
feature preparation, training, evaluation, model registry, and an HTTP service.

## Layout

- `src/ml/tasks/` contains the pipeline stages used by the Airflow DAG.
- `src/ml/serving.py` exposes health, reload, and prediction endpoints.
- `data/` contains the sample vehicle and reservation data.
- `notebooks/` contains the model exploration.

## Run

```bash
uv run --package ml pytest
uv run --package ml --extra serving uvicorn ml.serving:app --reload
```

The Airflow UI setup is documented in `apps/airflow-pipelines/README.md`.
