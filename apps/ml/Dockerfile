FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    ML_MODELS_DIR=/app/ml-output \
    ML_LOGS_DIR=/app/ml-output/logs
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/ml/pyproject.toml apps/ml/pyproject.toml
COPY apps/ml/src/ apps/ml/src/
RUN uv sync --frozen --no-dev --extra serving --package ml

EXPOSE 8000
CMD ["uvicorn", "ml.serving:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
