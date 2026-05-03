.DEFAULT_GOAL := help
PRE_COMMIT := uv run pre-commit
PYTHON_VERSION := 3.13

help: ## Show command list
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: deps hooks ## Install dependencies and git hooks

deps: ## Install dependencies
	uv sync

deps-up: ## Upgrade dependencies
	uv sync --upgrade

hooks: ## Install git hooks
	$(PRE_COMMIT) install

lint: lint-fix lint-chk ## Run formatting fixes and checks

lint-fix: ## Run manual-stage pre-commit fixes
	$(PRE_COMMIT) run --hook-stage manual --all-files >/dev/null || true

lint-chk: ## Run pre-commit checks
	$(PRE_COMMIT) run --hook-stage pre-commit --all-files

fmt: lint-fix ## Format source files

typecheck: ## Run type checks
	uv run ty check

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage
	uv run pytest --cov=src --cov-fail-under=90 --cov-report=term-missing

build: ## Build Python package artifacts
	uv build --no-sources

check: ## Run all project checks
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check
	uv run pytest --cov=src --cov-fail-under=90
	uv build --no-sources

clean: ## Remove caches and build artifacts
	rm -rf .coverage .pytest_cache .ruff_cache .venv .uv-cache build dist htmlcov
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
