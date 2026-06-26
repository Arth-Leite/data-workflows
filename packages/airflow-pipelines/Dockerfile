FROM apache/airflow:slim-3.2.2-python3.12

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/home/airflow/.local
WORKDIR /opt/airflow

# Cache the packages first - copy files later
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --inexact --no-install-project --package airflow-pipelines

COPY packages/airflow-pipelines/dags/ dags/
