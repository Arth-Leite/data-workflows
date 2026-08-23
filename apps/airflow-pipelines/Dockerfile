FROM apache/airflow:slim-3.2.2-python3.12

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/home/airflow/.local
WORKDIR /opt/airflow

# Cache the packages first - copy files later
COPY pyproject.toml uv.lock ./
COPY apps/airflow-pipelines/pyproject.toml apps/airflow-pipelines/pyproject.toml
COPY apps/airflow-pipelines/src/ apps/airflow-pipelines/src/
RUN uv sync --frozen --no-dev --inexact --package airflow-pipelines

COPY apps/airflow-pipelines/dags/ dags/
