FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/web-crawler/pyproject.toml apps/web-crawler/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-project --package web-crawler

COPY apps/web-crawler/ apps/web-crawler/
RUN uv sync --frozen --no-dev --package web-crawler

ENV PATH="/app/.venv/bin:$PATH"
