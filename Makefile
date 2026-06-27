.PHONY: help install install-dev dev-setup setup up up-postgres down restart logs logs-api logs-db ps build rebuild shell shell-db \
	init-db init-db-local migrate psql backup-db restore-db reset-db run-api run-api-docker ui-install run-ui local-dev local-quickstart \
	test test-verbose test-cov test-docker test-unit test-integration test-config \
	lint format type-check pgadmin health docs agents health-docker validate validate-azure validate-api-docker smoke-docker \
	clean clean-docker clean-all quickstart info recreate-api

.DEFAULT_GOAL := help

# --- Paths & services ---
COMPOSE_FILE := docker-compose.yml
API_SERVICE := api
DB_SERVICE := postgres
DB_NAME := ai_agents
DB_USER := postgres
ROOT := $(CURDIR)
SAMPLE_CSV := $(ROOT)/data/sample_job_metrics.csv
API_URL := http://localhost:8000

DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

# Prefer project venv when present
PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest

# Local test / validation env (override in shell if needed)
export USE_LOCAL_DATA ?= true
export LOCAL_DATA_PATH ?= $(SAMPLE_CSV)
export USE_MOCK_LLM ?= true
export CONFIG_DIR ?= $(ROOT)/config
export PYTHONPATH := $(ROOT)

BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m

##@ Help

help: ## Display this help message
	@echo "$(BLUE)EDIM DDE AI Agents - Makefile Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Usage:$(NC) make [target]"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-22s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup

install: ## Install Python dependencies locally
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-dev: ## Install dev dependencies (black, isort, pre-commit)
	@echo "$(BLUE)Installing dev dependencies...$(NC)"
	$(PIP) install -r requirements-dev.txt

dev-setup: ## One-shot dev setup: venv + deps + dev deps + pre-commit hook
	@echo "$(BLUE)=== Dev setup ===$(NC)"
	@if [ ! -d ".venv" ]; then \
		python3 -m venv .venv; \
		echo "$(GREEN)Virtual environment created$(NC)"; \
	else \
		echo "$(GREEN)Using existing .venv$(NC)"; \
	fi
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/pre-commit install
	@echo "$(GREEN)Dev setup complete.$(NC)"
	@echo "$(YELLOW)Activate venv: source .venv/bin/activate$(NC)"
	@echo "$(YELLOW)Local dev (Postgres Docker + host API/UI): make local-dev$(NC)"

setup: ## Create venv only (then: make install or make dev-setup)
	@echo "$(BLUE)Setting up project...$(NC)"
	@if [ ! -d ".venv" ]; then python3 -m venv .venv; echo "$(GREEN).venv created$(NC)"; fi
	@echo "$(YELLOW)Run: make dev-setup$(NC)"

##@ Docker

up: ## Start postgres + api (loads .env; optional az token injection)
	@echo "$(BLUE)Starting Docker services...$(NC)"
	@if command -v az >/dev/null 2>&1; then \
		export AZURE_OPENAI_ACCESS_TOKEN=$$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv 2>/dev/null) || true; \
		export DATABRICKS_TOKEN=$$(az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv 2>/dev/null) || true; \
	fi; \
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d postgres $(API_SERVICE)
	@echo "$(GREEN)Services started. API: $(API_URL)$(NC)"
	@echo "$(YELLOW)Recreate api after .env changes: make recreate-api$(NC)"

up-postgres: ## Start Postgres only (Docker); pair with run-api + run-ui on host
	@echo "$(BLUE)Starting Postgres (Docker only)...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d $(DB_SERVICE)
	@echo "$(GREEN)Postgres started on localhost:5432$(NC)"
	@echo "$(YELLOW)First time: make init-db-local$(NC)"
	@echo "$(YELLOW)Then: make run-api (terminal 2), make run-ui (terminal 3)$(NC)"

down: ## Stop all services (includes pgAdmin profile)
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --profile tools down
	@echo "$(GREEN)Services stopped$(NC)"

restart: ## Restart api + postgres
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) restart postgres $(API_SERVICE)

recreate-api: ## Recreate api container (pick up .env / compose env changes)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d --force-recreate $(API_SERVICE)

logs: ## Follow logs (all services)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f

logs-api: ## Follow API logs
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f $(API_SERVICE)

logs-db: ## Follow Postgres logs
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f $(DB_SERVICE)

ps: ## Show service status
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) ps

build: ## Build Docker images
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build

rebuild: ## Rebuild Docker images (no cache)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build --no-cache

shell: ## Shell in API container
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) /bin/bash \
		|| $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) /bin/sh

shell-db: ## psql in postgres container
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME)

##@ Database

init-db: ## Create/update tables via SQLAlchemy (api container must be running)
	@echo "$(BLUE)Initializing database schema...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) python scripts/migrate-db.py
	@echo "$(GREEN)Database initialized$(NC)"

init-db-local: ## Migrate schema from host (Postgres in Docker; API on host)
	@echo "$(BLUE)Initializing database schema (host)...$(NC)"
	USE_POSTGRES=true $(PYTHON) scripts/migrate-db.py
	@echo "$(GREEN)Database initialized$(NC)"

migrate: init-db ## Alias for init-db

psql: ## Connect to PostgreSQL (host via compose)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME)

backup-db: ## Dump database to backups/
	@mkdir -p backups
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T $(DB_SERVICE) pg_dump -U $(DB_USER) $(DB_NAME) > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)Backup saved under backups/$(NC)"

restore-db: ## Restore DB (usage: make restore-db FILE=backups/backup.sql)
	@if [ -z "$(FILE)" ]; then echo "$(YELLOW)Usage: make restore-db FILE=backups/backup.sql$(NC)"; exit 1; fi
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME) < $(FILE)

reset-db: ## Drop and recreate database (interactive confirm)
	@echo "$(YELLOW)WARNING: deletes all data$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -c "DROP DATABASE IF EXISTS $(DB_NAME);"; \
		$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -c "CREATE DATABASE $(DB_NAME);"; \
		$(MAKE) init-db; \
	fi

##@ Development

local-dev: ## Print local dev workflow (Postgres Docker + host API + UI)
	@echo "$(BLUE)Local development (use separate terminals):$(NC)"
	@echo "  1. make up-postgres"
	@echo "  2. make init-db-local          # first time only"
	@echo "  3. make run-api"
	@echo "  4. make ui-install && make run-ui"

local-quickstart: up-postgres init-db-local ## Postgres + migrate; then run-api and run-ui elsewhere
	@echo "$(GREEN)Postgres ready.$(NC)"
	@echo "$(YELLOW)Terminal 2: make run-api$(NC)"
	@echo "$(YELLOW)Terminal 3: make ui-install && make run-ui$(NC)"

run-api: ## Run API on host with hot reload (127.0.0.1:8000; loads .env)
	@echo "$(BLUE)Starting API (local)...$(NC)"
	@set -a; [ -f .env ] && . ./.env; set +a; \
	USE_POSTGRES=$${USE_POSTGRES:-true} $(PYTHON) -m uvicorn API.src.main:app --host 127.0.0.1 --port 8000 --reload

run-api-docker: ## Foreground api + postgres (compose)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up postgres $(API_SERVICE)

ui-install: ## npm install in UI/
	cd UI && npm install

run-ui: ## Angular dev server (http://localhost:4200)
	cd UI && npm start

##@ Testing

test: ## Run all tests (mock LLM, local CSV, no postgres)
	@echo "$(BLUE)Running tests...$(NC)"
	@echo "$(YELLOW)USE_MOCK_LLM=$(USE_MOCK_LLM) LOCAL_DATA_PATH=$(LOCAL_DATA_PATH)$(NC)"
	USE_POSTGRES=false $(PYTEST) -q

test-verbose: ## Run all tests (verbose)
	$(PYTEST) -v --tb=short

test-cov: ## Tests with coverage report
	$(PYTEST) --cov=. --cov-report=html --cov-report=term
	@echo "$(GREEN)Coverage: htmlcov/index.html$(NC)"

test-config: ## Config loader tests only
	$(PYTEST) shared/tests/test_config_loader.py -v

test-docker: ## Run tests inside api image
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --rm \
		-e USE_LOCAL_DATA=true \
		-e LOCAL_DATA_PATH=/app/data/sample_job_metrics.csv \
		-e USE_POSTGRES=false \
		-e USE_MOCK_LLM=true \
		-e CONFIG_DIR=/app/config \
		$(API_SERVICE) pytest -q --tb=short

test-unit: ## Run tests marked unit (or fallback paths)
	$(PYTEST) -m unit -v 2>/dev/null || $(PYTEST) DE/tests AI/tests API/tests shared/tests -v

test-integration: ## Run tests marked integration
	$(PYTEST) -m integration -v 2>/dev/null || echo "$(YELLOW)No @pytest.mark.integration tests$(NC)"

##@ Validation (pre-Phase 5)

validate: test ## Local validation: unit tests + config tests
	@echo "$(GREEN)Local validate passed$(NC)"

validate-azure: ## Real Azure OpenAI + recommendation (requires .env secrets; no mock)
	@echo "$(BLUE)Azure OpenAI validation (real LLM)...$(NC)"
	USE_MOCK_LLM= USE_POSTGRES=false LOCAL_DATA_PATH=$(SAMPLE_CSV) $(PYTHON) scripts/validate_azure_openai_recommendations.py

validate-crud: ## Full API CRUD/read validation (stack must be up: make up)
	@bash scripts/validate_api_crud.sh

validate-api-docker: ## HTTP smoke against running docker API (mock LLM)
	@echo "$(BLUE)Docker API smoke (mock LLM)...$(NC)"
	API_BASE=$(API_URL) bash scripts/validate_recommendations_api.sh

smoke-docker: ## Start stack, health + agents + profile CRUD smoke, then stop
	@echo "$(BLUE)Docker smoke test...$(NC)"
	@$(MAKE) up
	@sleep 3
	@$(MAKE) health-docker
	@$(MAKE) agents
	@curl -sf -X POST $(API_URL)/api/agent-profiles/ \
		-H 'content-type: application/json' \
		-d '{"agent_id":"job_run_cluster_sizing","name":"MakefileSmoke","overrides":{"rag":{"backend":"none"}}}' \
		| $(PYTHON) -m json.tool
	@echo "$(GREEN)smoke-docker passed$(NC)"

##@ Code Quality

lint: ## Run ruff or flake8 if installed
	@if command -v ruff >/dev/null 2>&1; then ruff check .; \
	elif command -v flake8 >/dev/null 2>&1; then flake8 .; \
	else echo "$(YELLOW)Install ruff or flake8$(NC)"; exit 1; fi

format: ## Format with isort + black (.venv preferred)
	@[ -x .venv/bin/isort ] && ISORT=.venv/bin/isort || ISORT=$$(command -v isort); \
	[ -x .venv/bin/black ] && BLACK=.venv/bin/black || BLACK=$$(command -v black); \
	$$ISORT . && $$BLACK .

type-check: ## Run mypy if installed
	@command -v mypy >/dev/null 2>&1 && mypy . || echo "$(YELLOW)mypy not installed$(NC)"

##@ Tools

pgadmin: ## Start pgAdmin (profile tools)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --profile tools up -d pgadmin
	@echo "$(GREEN)http://localhost:5050$(NC)"

health: ## GET /api/health (local URL)
	@curl -sf $(API_URL)/api/health/ | $(PYTHON) -m json.tool || echo "$(YELLOW)API not running at $(API_URL)$(NC)"

health-docker: health ## Alias: health check against docker-published port

agents: ## List registered agent IDs
	@curl -sf $(API_URL)/api/agents/ | $(PYTHON) -m json.tool

agent-profiles: ## List agent profiles (optional: AGENT_ID=job_run_cluster_sizing)
	@curl -sf "$(API_URL)/api/agent-profiles/?agent_id=$${AGENT_ID:-}" | $(PYTHON) -m json.tool

docs: ## Open Swagger UI
	@command -v open >/dev/null && open $(API_URL)/docs || echo "$(YELLOW)$(API_URL)/docs$(NC)"

##@ Cleanup

clean: ## Remove Python cache files
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

clean-docker: ## docker compose down -v (interactive)
	@echo "$(YELLOW)Removes containers and volumes$(NC)"
	@read -p "Continue? [y/N] " -n 1 -r; echo; \
	[[ $$REPLY =~ ^[Yy]$$ ]] && $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down -v

clean-all: clean ## clean + optional docker (run clean-docker separately)

##@ Quick Start

quickstart: up init-db health ## Start docker, init DB, health check
	@echo "$(GREEN)API: $(API_URL)/docs$(NC)"

##@ Information

info: ## Show versions and compose status
	@echo "$(BLUE)Python:$(NC) $$($(PYTHON) --version 2>/dev/null)"
	@echo "$(BLUE)Docker:$(NC) $$(docker --version 2>/dev/null)"
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) ps 2>/dev/null || true
