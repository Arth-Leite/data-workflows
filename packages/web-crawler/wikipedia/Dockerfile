FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/web-crawler/pyproject.toml packages/web-crawler/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-project --package web-crawler

COPY packages/web-crawler/ packages/web-crawler/
RUN uv sync --frozen --no-dev --package web-crawler

ENV PATH="/app/.venv/bin:$PATH"
