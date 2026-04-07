# Makefile for claude-md-compiler
# Usage: `make <target>`. Run `make help` for the full target list.

.DEFAULT_GOAL := help
.PHONY: help install test lint fmt fmt-check typecheck cover build clean smoke all

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Sync the locked dev environment
	uv sync --locked

test: ## Run the full pytest suite (quiet)
	uv run pytest -q

lint: ## Run ruff lint checks against src + tests
	uvx --from 'ruff>=0.6' ruff check src tests

fmt: ## Run ruff format against src + tests (writes changes)
	uvx --from 'ruff>=0.6' ruff format src tests

fmt-check: ## Verify src + tests are already ruff-formatted
	uvx --from 'ruff>=0.6' ruff format --check src tests

typecheck: ## Run pyright against src
	uvx --from 'pyright>=1.1' pyright src

cover: ## Run pytest with coverage report (term-missing)
	uv run --with pytest-cov pytest --cov=cldc --cov-report=term-missing

build: ## Build wheel + sdist into dist/
	rm -rf dist/
	uv build --clear

smoke: build ## Smoke-test the freshly-built wheel in an isolated env
	uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py

clean: ## Remove build, cache, and coverage artifacts
	rm -rf dist/ .pytest_cache/ .coverage coverage.xml .benchmarks/
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '.mypy_cache' -prune -exec rm -rf {} +
	find . -type d -name '.ruff_cache' -prune -exec rm -rf {} +

all: install lint fmt-check typecheck test build smoke ## Run the full local quality gate
