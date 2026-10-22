.DEFAULT_GOAL := help
.PHONY: help test api

help:
	@echo "make test"
	@echo "make api"

test:
	uv run --package ml pytest

api:
	uv run --package ml --extra serving uvicorn ml.serving:app --reload
