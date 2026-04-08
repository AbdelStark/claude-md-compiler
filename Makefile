# Makefile for claude-md-compiler
# Usage: `make <target>`. Run `make help` for the full target list.

.DEFAULT_GOAL := help
.PHONY: help install test e2e e2e-fast e2e-interactive e2e-test lint fmt fmt-check typecheck cover build clean smoke tui all

E2E_DEMO_ARGS ?= --pause-seconds 1.25

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Sync the locked dev environment
	uv sync --locked

test: ## Run the full pytest suite (quiet, excludes e2e and benchmarks)
	uv run pytest -q

e2e: ## Launch the narrated e2e demo against langchain
	uv run python -m tests.e2e.demo $(E2E_DEMO_ARGS)

e2e-fast: ## Launch the narrated e2e demo with no automatic pauses
	uv run python -m tests.e2e.demo --pause-seconds 0

e2e-interactive: ## Launch the narrated e2e demo and wait for a keypress between stages
	uv run python -m tests.e2e.demo --interactive --pause-seconds 0

e2e-test: ## Run the raw pytest e2e regression suite against real upstream repos
	uv run pytest -m e2e -v

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
	uv build

smoke: build ## Smoke-test the freshly-built wheel in an isolated env
	uv run --isolated --no-project --with dist/*.whl tests/smoke_test.py

tui: ## Launch the interactive TUI against tests/fixtures/repo_a
	uv run cldc tui tests/fixtures/repo_a

clean: ## Remove build, cache, and coverage artifacts
	rm -rf dist/ .pytest_cache/ .coverage coverage.xml .benchmarks/
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '.mypy_cache' -prune -exec rm -rf {} +
	find . -type d -name '.ruff_cache' -prune -exec rm -rf {} +

all: install lint fmt-check typecheck test build smoke ## Run the full local quality gate
