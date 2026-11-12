.DEFAULT_GOAL := help
.NOTPARALLEL:

TEST_WORKERS ?= 1
PLAYWRIGHT_WORKERS ?= 1
COMPOSE_PARALLEL_LIMIT ?= 1
NODE_MAX_OLD_SPACE_SIZE ?= 1536
PYTHON ?= .venv/bin/python

.PHONY: help setup lock dev scheduler assets migrate superuser test test-playwright lint format status backup build docker-migrate docker-up docker-down docker-logs dev-check deploy-check nginx-check docs-check cli-dist verify
help:
	@echo "Comandos: setup dev scheduler assets migrate superuser test test-playwright lint format status backup build docker-migrate docker-up docker-down docker-logs dev-check deploy-check nginx-check docs-check cli-dist verify"

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.lock
	.venv/bin/pip install -e . --no-deps

lock:
	.venv/bin/pip freeze --exclude-editable > requirements.lock

dev:
	$(PYTHON) manage.py runserver

scheduler:
	$(PYTHON) manage.py run_scheduler

migrate:
	mkdir -p data
	$(PYTHON) manage.py migrate
	$(PYTHON) manage.py seed_market_pipeline

superuser:
	$(PYTHON) manage.py createsuperuser

test:
	$(PYTHON) -m pytest -m "not playwright"

test-playwright:
	$(PYTHON) -m pytest -m playwright

lint:
	$(PYTHON) -m ruff check src tests manage.py

format:
	$(PYTHON) -m ruff format src tests manage.py

assets:
	NODE_OPTIONS=--max-old-space-size=$(NODE_MAX_OLD_SPACE_SIZE) corepack pnpm --dir frontend install --frozen-lockfile --network-concurrency 4
	NODE_OPTIONS=--max-old-space-size=$(NODE_MAX_OLD_SPACE_SIZE) corepack pnpm --dir frontend build

build:
	COMPOSE_PARALLEL_LIMIT=$(COMPOSE_PARALLEL_LIMIT) docker compose build

docker-migrate:
	docker compose run --rm web python manage.py migrate
	docker compose run --rm web python manage.py seed_market_pipeline

docker-up:
	docker compose up -d web scheduler

docker-down:
	docker compose down

docker-logs:
	docker compose logs --no-color --tail=100 web scheduler

dev-check:
	scripts/dev-bootstrap.sh --check

deploy-check:
	scripts/deploy-production.sh --check

nginx-check:
	scripts/check-nginx-config.sh

docs-check:
	bash -n scripts/dev-bootstrap.sh scripts/deploy-production.sh scripts/check-nginx-config.sh scripts/check-doc-links.sh
	python3 -m py_compile scripts/check_doc_links.py scripts/build_cli_dist.py
	docker compose --env-file .env.production.example config --quiet
	@test -f Makefile.ps1
	@test -f scripts/dev-bootstrap.ps1
	@test -f scripts/deploy-production.ps1
	@test -f docs/development/README.md
	@test -f docs/development/LINUX.md
	@test -f docs/development/WINDOWS.md
	@test -f docs/development/ENVIRONMENT_VARIABLES.md
	@test -f docs/operations/PRODUCTION.md
	@test -f docs/project/PROJECT_EFFORT.md
	@test -f docs/development/DEVELOPMENT.md
	@test -f docs/operations/DEPLOYMENT_NGINX.md
	@test -f docs/README.md
	@test -f docs/TECHNOLOGY_STACK.md
	@test -f docs/ARCHITECTURE.md
	@test -f docs/REPOSITORY_STRUCTURE.md
	@test -f docs/cli/CLI_ARCHITECTURE.md
	@test -f docs/cli/CLI_CONFIG.md
	@test -f docs/cli/CLI_LEER_PRIMERO.md
	@test -f docs/cli/CLI_USAGE.md
	@test -f docs/cli/CLI_OUTPUT_SCHEMAS.md
	@test -f docs/cli/CLI_DISTRIBUTION.md
	@test -f docs/data/DATA_PIPELINE.md
	@test -f docs/data/DATA_CLEANING.md
	@test -f docs/data/DATA_TRANSFORMATION.md
	@test -f docs/development/WINDOWS_LINUX.md
	@test -f AGENTS.md
	@test -f cli_dist/requirements.txt
	@test -f cli_dist/README.md
	@test -f cli_dist/THIRD_PARTY_NOTICES.md
	@test -f cli_dist/run.py
	@python3 scripts/check_doc_links.py

cli-dist:
	$(PYTHON) scripts/build_cli_dist.py --output dist/scraper-cli

backup:
	$(PYTHON) manage.py backup_sqlite

verify:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) assets
	$(MAKE) test-playwright
	$(MAKE) build

status:
	@echo "== Git =="
	@git status --short
	@echo "== Tarea en curso =="
	@grep -n -- "^- \[-\]" docs/IMPLEMENTATION_PLAN.md || true
	@echo "== Primeras tareas pendientes =="
	@grep -n -- "^- \[ \]" docs/IMPLEMENTATION_PLAN.md | head -5 || true
	@echo "== Progreso =="
	@sed -n '1,12p' docs/PROGRESS.md
	@echo "== Comandos =="
	@$(MAKE) --no-print-directory help
