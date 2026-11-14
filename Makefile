# FireTwin Makefile (OPS-01): one entry point for every layer.
# At Phase 0 most layers are still empty, so each target first checks that its files exist
# and prints a "skipping" message instead of failing.
# Recipe lines MUST start with a real TAB character, not spaces, or make refuses to run.

# bash (not the default sh) so `dev` can use `trap` and `jobs` reliably.
SHELL := /bin/bash

# Pass .env to `uv run` only when it exists: a fresh clone has just .env.example.
ENV_FILE := $(if $(wildcard .env),--env-file .env,)

# Plain `make` shows the help instead of running something by surprise.
.DEFAULT_GOAL := help
# These are command names, not files, so make always runs them.
.PHONY: help setup data train dev test lint

help: ## Show this list of targets
	@echo "FireTwin make targets:"
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  make %-6s %s\n", $$1, $$2}'

setup: ## Install Python deps (uv) and frontend deps (npm, once the frontend exists)
	uv sync
	@if [ -f frontend/package.json ]; then \
		echo "setup: installing frontend packages (npm ci)"; \
		cd frontend && npm ci; \
	else \
		echo "setup: skipping frontend (no frontend/package.json yet, FE-01)"; \
	fi

data: ## Run the data pipeline: download -> clean_* -> build_table
	@# Runs whichever pipeline scripts exist, in order; stops at the first one that fails.
	@ran=0; \
	for script in data/pipeline/download.py data/pipeline/clean_*.py data/pipeline/build_table.py; do \
		if [ -f "$$script" ]; then \
			echo "data: running $$script"; \
			uv run $(ENV_FILE) python "$$script" || exit 1; \
			ran=1; \
		fi; \
	done; \
	if [ $$ran -eq 0 ]; then \
		echo "data: skipping (no scripts in data/pipeline/ yet, DAT-03/04/05)"; \
	fi

train: ## Train the burn model (ml/train.py writes ml/artifacts/)
	@if [ -f ml/train.py ]; then \
		uv run $(ENV_FILE) python ml/train.py; \
	else \
		echo "train: skipping (no ml/train.py yet, ML-01)"; \
	fi

dev: ## Start backend (:8000) and frontend (:5173) dev servers; Ctrl+C stops both
	@if [ ! -f backend/app/main.py ] && [ ! -f frontend/package.json ]; then \
		echo "dev: skipping (no backend/app/main.py (BE-05) or frontend/package.json (FE-01) yet)"; \
		exit 0; \
	fi; \
	trap 'kill $$(jobs -p) 2>/dev/null' INT TERM EXIT; \
	if [ -f backend/app/main.py ]; then \
		echo "dev: backend on http://localhost:8000"; \
		uv run $(ENV_FILE) uvicorn app.main:app --app-dir backend --reload --port 8000 & \
	else \
		echo "dev: skipping backend (no backend/app/main.py yet, BE-05)"; \
	fi; \
	if [ -f frontend/package.json ]; then \
		echo "dev: frontend on http://localhost:5173"; \
		(cd frontend && npm run dev) & \
	else \
		echo "dev: skipping frontend (no frontend/package.json yet, FE-01)"; \
	fi; \
	wait

test: ## Run all pytest suites (data, ml, backend, repo-wide)
	@# No --env-file here on purpose: tests must never see real API keys.
	uv run pytest

lint: ## Check Python code: ruff lint rules, then formatting
	uv run ruff check .
	uv run ruff format --check .
