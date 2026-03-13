.PHONY: help install install-dev dev-setup setup up down restart logs shell test clean migrate init-db backup-db restore-db lint format run-api build rebuild psql pgadmin

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE_FILE := docker-compose.yml
API_SERVICE := api
DB_SERVICE := postgres
DB_NAME := ai_agents
DB_USER := postgres

# Detect docker-compose command (v1 uses docker-compose, v2 uses docker compose)
DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

##@ Help

help: ## Display this help message
	@echo "$(BLUE)EDIM DDE AI Agents - Makefile Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Usage:$(NC) make [target]"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Setup

install: ## Install Python dependencies locally
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	pip install --upgrade pip
	pip install -r requirements.txt

install-dev: ## Install dev dependencies (black, isort, pre-commit)
	@echo "$(BLUE)Installing dev dependencies...$(NC)"
	pip install -r requirements-dev.txt

dev-setup: ## One-shot dev setup: venv + deps + dev deps + pre-commit hook
	@echo "$(BLUE)=== Dev setup ===$(NC)"
	@if [ ! -d ".venv" ]; then \
		python3 -m venv .venv; \
		echo "$(GREEN)Virtual environment created$(NC)"; \
	else \
		echo "$(GREEN)Using existing .venv$(NC)"; \
	fi
	@echo "$(BLUE)Installing dependencies...$(NC)"
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -r requirements-dev.txt
	@echo "$(BLUE)Installing pre-commit hook...$(NC)"
	.venv/bin/pre-commit install
	@echo "$(GREEN)Dev setup complete.$(NC)"
	@echo "$(YELLOW)Activate venv: source .venv/bin/activate$(NC)"
	@echo "$(YELLOW)Then run: make test, make format, etc.$(NC)"

setup: ## Initial project setup (create venv and install dependencies)
	@echo "$(BLUE)Setting up project...$(NC)"
	@if [ ! -d ".venv" ]; then \
		python3 -m venv .venv; \
		echo "$(GREEN)Virtual environment created$(NC)"; \
	fi
	@echo "$(BLUE)Activate with: source .venv/bin/activate$(NC)"
	@echo "$(BLUE)Then run: make install$(NC)"
	@echo "$(BLUE)Or run: make dev-setup (venv + deps + dev tools + pre-commit)$(NC)"

##@ Docker

up: ## Start all Docker services (fetches Azure access token for container if 'az' is available)
	@echo "$(BLUE)Starting Docker services...$(NC)"
	@if command -v az >/dev/null 2>&1; then \
		echo "$(BLUE)Fetching Azure access token for container...$(NC)"; \
		export AZURE_OPENAI_ACCESS_TOKEN=$$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv 2>/dev/null) || true; \
		if [ -n "$$AZURE_OPENAI_ACCESS_TOKEN" ]; then echo "$(GREEN)Token set for AZURE_OPENAI_ACCESS_TOKEN$(NC)"; else echo "$(YELLOW)No token (run 'az login' if needed); container will use API key or DefaultAzureCredential$(NC)"; fi; \
	fi; \
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up -d
	@echo "$(GREEN)Services started. Use 'make logs' to view logs$(NC)"

down: ## Stop all Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down
	@echo "$(GREEN)Services stopped$(NC)"

restart: ## Restart all Docker services
	@echo "$(BLUE)Restarting Docker services...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) restart
	@echo "$(GREEN)Services restarted$(NC)"

logs: ## View logs from all services (follow mode)
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f

logs-api: ## View logs from API service only
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f $(API_SERVICE)

logs-db: ## View logs from PostgreSQL service only
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) logs -f $(DB_SERVICE)

ps: ## Show status of Docker services
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) ps

build: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build
	@echo "$(GREEN)Build complete$(NC)"

rebuild: ## Rebuild Docker images (no cache)
	@echo "$(BLUE)Rebuilding Docker images (no cache)...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build --no-cache
	@echo "$(GREEN)Rebuild complete$(NC)"

shell: ## Open shell in API container
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) /bin/bash || $(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) /bin/sh

shell-db: ## Open PostgreSQL shell
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME)

##@ Database

init-db: ## Initialize database schema (run migrations)
	@echo "$(BLUE)Initializing database...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(API_SERVICE) python scripts/migrate-db.py
	@echo "$(GREEN)Database initialized$(NC)"

migrate: init-db ## Alias for init-db

psql: ## Connect to PostgreSQL database
	@echo "$(BLUE)Connecting to PostgreSQL...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME)

backup-db: ## Backup PostgreSQL database
	@echo "$(BLUE)Backing up database...$(NC)"
	@mkdir -p backups
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T $(DB_SERVICE) pg_dump -U $(DB_USER) $(DB_NAME) > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)Backup saved to backups/$(NC)"

restore-db: ## Restore PostgreSQL database (usage: make restore-db FILE=backups/backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "$(YELLOW)Error: FILE variable required$(NC)"; \
		echo "Usage: make restore-db FILE=backups/backup.sql"; \
		exit 1; \
	fi
	@echo "$(BLUE)Restoring database from $(FILE)...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec -T $(DB_SERVICE) psql -U $(DB_USER) -d $(DB_NAME) < $(FILE)
	@echo "$(GREEN)Database restored$(NC)"

reset-db: ## Reset database (drop and recreate - WARNING: deletes all data)
	@echo "$(YELLOW)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -c "DROP DATABASE IF EXISTS $(DB_NAME);"; \
		$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) exec $(DB_SERVICE) psql -U $(DB_USER) -c "CREATE DATABASE $(DB_NAME);"; \
		$(MAKE) init-db; \
		echo "$(GREEN)Database reset complete$(NC)"; \
	fi

##@ Development

run-api: ## Run API locally (without Docker)
	@echo "$(BLUE)Starting API server...$(NC)"
	uvicorn API.src.main:app --host 0.0.0.0 --port 8000 --reload

run-api-docker: ## Run API in Docker (with hot-reload)
	@echo "$(BLUE)Starting API in Docker...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) up $(API_SERVICE)

##@ Testing

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	pytest

test-verbose: ## Run tests with verbose output
	pytest -v

test-cov: ## Run tests with coverage report
	pytest --cov=. --cov-report=html --cov-report=term
	@echo "$(GREEN)Coverage report generated in htmlcov/index.html$(NC)"

test-docker: ## Run tests in Docker container (starts postgres + api as needed)
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --rm $(API_SERVICE) pytest -v --tb=short

test-unit: ## Run unit tests only (uses pytest.ini testpaths)
	pytest -m unit -v 2>/dev/null || pytest DE/tests AI/tests API/tests -v

test-integration: ## Run integration tests only
	pytest -m integration -v 2>/dev/null || echo "$(YELLOW)No integration tests found. Add @pytest.mark.integration to tests$(NC)"

##@ Code Quality

lint: ## Run linter
	@echo "$(BLUE)Running linter...$(NC)"
	@if command -v ruff > /dev/null; then \
		ruff check .; \
	elif command -v flake8 > /dev/null; then \
		flake8 .; \
	else \
		echo "$(YELLOW)Linter not installed. Install ruff or flake8$(NC)"; \
	fi

format: ## Format code with black and isort (uses .venv if present)
	@echo "$(BLUE)Formatting code...$(NC)"
	@[ -x .venv/bin/isort ] && ISORT=.venv/bin/isort || ISORT=$$(command -v isort 2>/dev/null); \
	if [ -z "$$ISORT" ]; then \
		echo "$(YELLOW)isort not found. Run: make dev-setup$(NC)"; exit 1; \
	fi; \
	"$$ISORT" . && echo "$(GREEN)Imports sorted$(NC)"
	@[ -x .venv/bin/black ] && BLACK=.venv/bin/black || BLACK=$$(command -v black 2>/dev/null); \
	if [ -z "$$BLACK" ]; then \
		echo "$(YELLOW)black not found. Run: make dev-setup$(NC)"; exit 1; \
	fi; \
	"$$BLACK" . && echo "$(GREEN)Code formatted$(NC)"

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checker...$(NC)"
	@if command -v mypy > /dev/null; then \
		mypy .; \
	else \
		echo "$(YELLOW)MyPy not installed. Install with: pip install mypy$(NC)"; \
	fi

##@ Tools

pgadmin: ## Start pgAdmin (database management UI)
	@echo "$(BLUE)Starting pgAdmin...$(NC)"
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) --profile tools up -d pgadmin
	@echo "$(GREEN)pgAdmin started at http://localhost:5050$(NC)"
	@echo "$(YELLOW)Email: admin@example.com$(NC)"
	@echo "$(YELLOW)Password: admin$(NC)"

health: ## Check API health
	@echo "$(BLUE)Checking API health...$(NC)"
	@curl -s http://localhost:8000/api/health/ | python3 -m json.tool || echo "$(YELLOW)API not running$(NC)"

docs: ## Open API documentation in browser
	@echo "$(BLUE)Opening API docs...$(NC)"
	@if command -v open > /dev/null; then \
		open http://localhost:8000/docs; \
	elif command -v xdg-open > /dev/null; then \
		xdg-open http://localhost:8000/docs; \
	else \
		echo "$(YELLOW)Visit http://localhost:8000/docs in your browser$(NC)"; \
	fi

##@ Cleanup

clean: ## Remove Python cache files
	@echo "$(BLUE)Cleaning Python cache...$(NC)"
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	@echo "$(GREEN)Cache cleaned$(NC)"

clean-docker: ## Remove Docker containers and volumes
	@echo "$(YELLOW)WARNING: This will remove all containers and volumes!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) down -v; \
		echo "$(GREEN)Docker resources cleaned$(NC)"; \
	fi

clean-all: clean clean-docker ## Remove all cache and Docker resources
	@echo "$(GREEN)All cleanup complete$(NC)"

##@ Quick Start

quickstart: ## Quick start guide - setup and start everything
	@echo "$(BLUE)=== Quick Start ===$(NC)"
	@echo ""
	@echo "$(GREEN)1. Starting Docker services...$(NC)"
	@$(MAKE) up
	@echo ""
	@echo "$(GREEN)2. Waiting for services to be ready...$(NC)"
	@sleep 5
	@echo ""
	@echo "$(GREEN)3. Initializing database...$(NC)"
	@$(MAKE) init-db
	@echo ""
	@echo "$(GREEN)4. Checking API health...$(NC)"
	@$(MAKE) health
	@echo ""
	@echo "$(BLUE)=== Setup Complete ===$(NC)"
	@echo "$(GREEN)API: http://localhost:8000$(NC)"
	@echo "$(GREEN)API Docs: http://localhost:8000/docs$(NC)"
	@echo "$(GREEN)PostgreSQL: localhost:5432$(NC)"
	@echo ""
	@echo "$(YELLOW)Use 'make logs' to view logs$(NC)"
	@echo "$(YELLOW)Use 'make help' to see all commands$(NC)"

##@ Information

info: ## Show project information
	@echo "$(BLUE)=== Project Information ===$(NC)"
	@echo ""
	@echo "$(GREEN)Project:$(NC) EDIM DDE AI Agents"
	@echo "$(GREEN)Python:$(NC) $$(python3 --version 2>/dev/null || echo 'Not found')"
	@echo "$(GREEN)Docker:$(NC) $$(docker --version 2>/dev/null || echo 'Not found')"
	@echo "$(GREEN)Docker Compose:$(NC) $$($(DOCKER_COMPOSE) --version 2>/dev/null || echo 'Not found')"
	@echo ""
	@echo "$(GREEN)Services:$(NC)"
	@$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) ps 2>/dev/null || echo "  Services not running"
	@echo ""
	@echo "$(GREEN)Use 'make help' for available commands$(NC)"

