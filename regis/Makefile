PY := python
PIP := pip
NPM := npm
BACKEND := backend

.PHONY: help install-dev precommit-install up dev lint format test build-frontend ci-check

help:
	@echo "Makefile targets:"
	@echo "  make install-dev       -> install backend dev dependencies"
	@echo "  make precommit-install -> install & enable pre-commit hooks"
	@echo "  make up                -> docker compose up (build)"
	@echo "  make dev               -> run scripts/dev.sh (full dev flow)"
	@echo "  make lint              -> run ruff + black --check + isort --check"
	@echo "  make format            -> run ruff --fix + black + isort"
	@echo "  make test              -> run backend pytest"
	@echo "  make build-frontend    -> npm ci && npm run build in frontend"
	@echo "  make ci-check          -> run CI checks locally"

install-dev:
	cd $(BACKEND) && $(PY) -m pip install --upgrade pip && $(PIP) install -e ."[dev]"

precommit-install:
	cd $(BACKEND) && $(PIP) install pre-commit && pre-commit install

up:
	docker compose up --build -d

dev:
	./scripts/dev.sh

lint:
	cd $(BACKEND) && ruff check . && black --check . && isort --check-only .

format:
	cd $(BACKEND) && ruff check . --fix && isort . && black .

test:
	cd $(BACKEND) && pytest -q

build-frontend:
	cd frontend && $(NPM) ci && $(NPM) run build

ci-check:
	cd $(BACKEND) && ruff check . && black --check . && isort --check-only . && python -m mypy app || true
