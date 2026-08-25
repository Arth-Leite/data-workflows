# Pinned: python:3.13-slim is a floating tag and moves on Debian security rebuilds, busting the build cache.
FROM python:3.13-slim@sha256:7e3a6aca9d74f93cca21a91d86a8dad8c34749afd5b4a98ee481c9c47b9f5ed4

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/web-crawler/pyproject.toml apps/web-crawler/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-project --package web-crawler

COPY apps/web-crawler/ apps/web-crawler/
RUN uv sync --frozen --no-dev --package web-crawler

ENV PATH="/app/.venv/bin:$PATH"
