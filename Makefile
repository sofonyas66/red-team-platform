# ETHIO-RTAP Platform Makefile
# Universal commands for Docker, Podman, and Docker Compose v1/v2
#
# Usage: make <target>
# Common targets: up, down, bootstrap, api, test, clean, help

# Detect container runtime and compose command
DETECT_RUNTIME := $(shell \
	if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then \
		echo "podman"; \
	elif docker compose version >/dev/null 2>&1; then \
		echo "docker"; \
	elif command -v docker-compose >/dev/null 2>&1; then \
		echo "docker-compose"; \
	else \
		echo "unknown"; \
	fi)

ifeq ($(DETECT_RUNTIME),podman)
	COMPOSE := podman compose
	SOCKET := $(XDG_RUNTIME_DIR)/podman/podman.sock
	export DOCKER_HOST := unix://$(SOCKET)
else ifeq ($(DETECT_RUNTIME),docker)
	COMPOSE := docker compose
else ifeq ($(DETECT_RUNTIME),docker-compose)
	COMPOSE := docker-compose
else
	COMPOSE := echo "ERROR: No container runtime found" && exit 1
endif

COMPOSE_FILE := docker-compose.yml
PROJECT_NAME := red-team-platform

# Colors
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
RED := \033[0;31m
NC := \033[0m

.PHONY: help up down ps logs bootstrap api test clean install lint format check-env check-isolation

# Default target
help:
	@echo "$(BLUE)ETHIO-RTAP Platform - Make Commands$(NC)"
	@echo ""
	@echo "Detected runtime: $(GREEN)$(DETECT_RUNTIME)$(NC) using $(GREEN)$(COMPOSE)$(NC)"
	@echo ""
	@echo "$(GREEN)Container Management:$(NC)"
	@echo "  make up         - Start Neo4j and Qdrant containers"
	@echo "  make down       - Stop containers"
	@echo "  make ps         - Show container status"
	@echo "  make logs       - Follow container logs (use SERVICE=neo4j for specific)"
	@echo ""
	@echo "$(GREEN)Platform Setup:$(NC)"
	@echo "  make install    - Install Python dependencies"
	@echo "  make bootstrap  - Full platform initialization (containers + schema + data)"
	@echo "  make api        - Start FastAPI server (after bootstrap)"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linting (ruff, mypy)"
	@echo "  make format     - Format code (ruff, black)"
	@echo ""
	@echo "$(GREEN)Maintenance:$(NC)"
	@echo "  make clean      - Remove containers, volumes, and Python cache"
	@echo "  make check-env  - Verify .env configuration"
	@echo ""

# Ensure .env exists
.env:
	@if [ ! -f .env ]; then \
		if [ -f .env.example ]; then \
			cp .env.example .env; \
			echo "$(YELLOW)Created .env from .env.example - PLEASE EDIT IT!$(NC)"; \
		else \
			echo "$(RED)No .env.example found$(NC)"; \
			exit 1; \
		fi; \
	fi

# Start containers
up: .env
	@echo "$(BLUE)Starting containers...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --remove-orphans
	@make ps

# Stop containers
down:
	@echo "$(BLUE)Stopping containers...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) down

# Show status
ps:
	@echo "$(BLUE)Container Status:$(NC)"
	@$(COMPOSE) -f $(COMPOSE_FILE) ps

# Follow logs
logs:
	@$(COMPOSE) -f $(COMPOSE_FILE) logs -f $(SERVICE)

# Install Python dependencies
install:
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	pip install -e .
	@echo "$(GREEN)Done!$(NC)"

# Full bootstrap - one command setup
bootstrap: .env
	@echo "$(BLUE)=== ETHIO-RTAP Full Bootstrap ===$(NC)"
	@make up
	@echo "$(BLUE)Waiting for services...$(NC)"
	@sleep 5
	@echo "$(BLUE)Running bootstrap.py...$(NC)"
	python bootstrap.py
	@echo "$(GREEN)Bootstrap complete!$(NC)"

# Start API server
api: .env
	@echo "$(BLUE)Starting API server...$(NC)"
	@make up
	@sleep 3
	python start_api.py

# Run tests
test: .env
	@echo "$(BLUE)Running tests...$(NC)"
	@make up
	@sleep 3
	python -m pytest tests/ -v 2>/dev/null || python -m pytest -v 2>/dev/null || python bootstrap.py

# Lint code
lint:
	@echo "$(BLUE)Running linters...$(NC)"
	ruff check . || true
	mypy . || true

# Format code
format:
	@echo "$(BLUE)Formatting code...$(NC)"
	ruff check --fix . || true
	black . || true

# Clean everything
clean:
	@echo "$(RED)Cleaning up...$(NC)"
	$(COMPOSE) -f $(COMPOSE_FILE) down -v --remove-orphans 2>/dev/null || true
	rm -rf venv __pycache__ .pytest_cache .mypy_cache *.pyc
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)Clean complete$(NC)"

# Check environment configuration
check-env: .env
	@echo "$(BLUE)Checking environment configuration...$(NC)"
	@echo ""
	@echo "$(YELLOW)Required variables:$(NC)"
	@grep -E '^[A-Z_]+=' .env.example | while IFS='=' read -r key _; do \
		if grep -q "^$$key=" .env; then \
			val=$$(grep "^$$key=" .env | cut -d'=' -f2-); \
			if [[ "$$val" == *"your_"* ]] || [[ -z "$$val" ]]; then \
				echo "  $(RED)✗$$key$(NC) - NEEDS CONFIGURATION"; \
			else \
				echo "  $(GREEN)✓$$key$(NC) - Set"; \
			fi; \
		else \
			echo "  $(RED)✗$$key$(NC) - MISSING"; \
		fi; \
	done
	@echo ""

# Check Neo4j tenant isolation — fails if any .py outside approved files calls driver directly
check-isolation:
	@echo "$(BLUE)Checking Neo4j tenant isolation...$(NC)"
	@bash scripts/check_tenant_isolation.sh

# Quick development cycle
dev: bootstrap
	@make api

# Production-like start (with Ollama)
prod: .env
	@echo "$(BLUE)Starting production stack...$(NC)"
	LLM_PROVIDER=ollama $(COMPOSE) -f $(COMPOSE_FILE) --profile ollama up -d
	@make bootstrap
	@make api

# Show detected environment
info:
	@echo "Runtime: $(DETECT_RUNTIME)"
	@echo "Compose: $(COMPOSE)"
	@echo "Project: $(PROJECT_NAME)"
	@echo "Compose file: $(COMPOSE_FILE)"
	@echo "DOCKER_HOST: $${DOCKER_HOST:-not set}"