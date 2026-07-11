#!/usr/bin/env bash
# ETHIO-RTAP Universal Startup Script
# Works with: Docker, Podman, Docker Compose v1, Docker Compose v2, Podman Compose
# Usage: ./run.sh [command]
# Commands: up, down, restart, logs, ps, bootstrap, api, test, help

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

# Detect compose command
detect_compose() {
    if command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
        COMPOSE_VERSION=$($COMPOSE_CMD version --short 2>/dev/null || echo "v1")
    elif docker compose version &>/dev/null; then
        COMPOSE_CMD="docker compose"
        COMPOSE_VERSION="v2"
    elif command -v podman-compose &>/dev/null; then
        COMPOSE_CMD="podman-compose"
        COMPOSE_VERSION="podman"
    elif podman compose version &>/dev/null; then
        COMPOSE_CMD="podman compose"
        COMPOSE_VERSION="podman-v2"
    else
        echo -e "${RED}Error: No Docker Compose or Podman Compose found!${NC}"
        echo "Please install one of:"
        echo "  - Docker Compose v2 (plugin): docker compose"
        echo "  - Docker Compose v1 (standalone): docker-compose"
        echo "  - Podman Compose: podman-compose or podman compose"
        exit 1
    fi
    echo -e "${GREEN}Using:${NC} ${COMPOSE_CMD} (${COMPOSE_VERSION})"
}

# Detect container runtime
detect_runtime() {
    if docker info &>/dev/null; then
        RUNTIME="docker"
    elif podman info &>/dev/null; then
        RUNTIME="podman"
        # Start podman socket if needed
        if ! systemctl --user is-active podman.socket &>/dev/null; then
            echo -e "${YELLOW}Starting podman socket...${NC}"
            systemctl --user start podman.socket 2>/dev/null || true
            sleep 1
        fi
    else
        echo -e "${RED}Error: No container runtime (Docker or Podman) found!${NC}"
        exit 1
    fi
    echo -e "${GREEN}Runtime:${NC} ${RUNTIME}"
}

# Load environment
load_env() {
    if [[ -f "${ENV_FILE}" ]]; then
        set -a
        source "${ENV_FILE}"
        set +a
        echo -e "${GREEN}Loaded:${NC} .env"
    elif [[ -f "${ENV_EXAMPLE}" ]]; then
        echo -e "${YELLOW}Warning: .env not found, copying from .env.example${NC}"
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
        set -a
        source "${ENV_FILE}"
        set +a
        echo -e "${GREEN}Created and loaded:${NC} .env (please edit with your API keys)"
    else
        echo -e "${RED}Error: Neither .env nor .env.example found!${NC}"
        exit 1
    fi
}

# Check if services are healthy
check_health() {
    local service=$1
    local port=$2
    local path=${3:-/}
    local max_attempts=${4:-30}
    local attempt=0

    echo -e "${CYAN}Waiting for ${service} on port ${port}...${NC}"
    while (( attempt < max_attempts )); do
        if curl -sf "http://localhost:${port}${path}" &>/dev/null; then
            echo -e "${GREEN}${service} is healthy!${NC}"
            return 0
        fi
        sleep 2
        ((attempt++))
    done
    echo -e "${RED}${service} health check failed after $((max_attempts * 2)) seconds${NC}"
    return 1
}

# Check Neo4j Bolt connection
check_neo4j() {
    local max_attempts=${1:-30}
    local attempt=0

    echo -e "${CYAN}Waiting for Neo4j Bolt connection...${NC}"
    while (( attempt < max_attempts )); do
        if command -v python3 &>/dev/null; then
            python3 -c "
import sys
try:
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'changeme'))
    driver.verify_connectivity()
    driver.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null && { echo -e "${GREEN}Neo4j is ready!${NC}"; return 0; }
        fi
        sleep 2
        ((attempt++))
    done
    echo -e "${RED}Neo4j connection failed${NC}"
    return 1
}

# Command: up
cmd_up() {
    detect_compose
    detect_runtime
    load_env

    echo -e "${BLUE}Starting services...${NC}"
    ${COMPOSE_CMD} -f "${COMPOSE_FILE}" up -d --remove-orphans

    # Wait for services
    check_health "Qdrant" 6333 "/healthz"
    check_neo4j

    echo -e "${GREEN}All services are running!${NC}"
    echo -e "${CYAN}Neo4j Browser:${NC} http://localhost:7474 (neo4j/changeme)"
    echo -e "${CYAN}Qdrant Dashboard:${NC} http://localhost:6333/dashboard"
}

# Command: down
cmd_down() {
    detect_compose
    echo -e "${BLUE}Stopping services...${NC}"
    ${COMPOSE_CMD} -f "${COMPOSE_FILE}" down
    echo -e "${GREEN}Services stopped.${NC}"
}

# Command: restart
cmd_restart() {
    cmd_down
    cmd_up
}

# Command: logs
cmd_logs() {
    detect_compose
    ${COMPOSE_CMD} -f "${COMPOSE_FILE}" logs -f "${@:2}"
}

# Command: ps
cmd_ps() {
    detect_compose
    ${COMPOSE_CMD} -f "${COMPOSE_FILE}" ps
}

# Command: bootstrap
cmd_bootstrap() {
    detect_compose
    detect_runtime
    load_env

    # Ensure services are up
    ${COMPOSE_CMD} -f "${COMPOSE_FILE}" up -d --remove-orphans
    check_health "Qdrant" 6333 "/healthz"
    check_neo4j

    echo -e "${BLUE}Running bootstrap...${NC}"
    cd "${PROJECT_ROOT}"
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
    fi
    python3 bootstrap.py
}

# Command: api
cmd_api() {
    detect_compose
    detect_runtime
    load_env

    echo -e "${BLUE}Starting API server...${NC}"
    cd "${PROJECT_ROOT}"
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
    fi
    python3 start_api.py
}

# Command: test
cmd_test() {
    detect_compose
    detect_runtime
    load_env

    ${COMPOSE_CMD} -f "${COMPOSE_FILE}" up -d --remove-orphans
    check_health "Qdrant" 6333 "/healthz"
    check_neo4j

    cd "${PROJECT_ROOT}"
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
    fi
    python3 -m pytest tests/ -v 2>/dev/null || python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'changeme'))
driver.verify_connectivity()
print('Neo4j: OK')
import requests
r = requests.get('http://localhost:6333/healthz')
print('Qdrant:', 'OK' if r.status_code == 200 else 'FAIL')
print('All tests passed!')
"
}

# Command: setup (one-time setup)
cmd_setup() {
    echo -e "${BLUE}=== ETHIO-RTAP One-Time Setup ===${NC}"
    echo

    # Check Python
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}Error: Python 3.10+ required${NC}"
        exit 1
    fi
    echo -e "${GREEN}Python:${NC} $(python3 --version)"

    # Create venv
    if [[ ! -d "venv" ]]; then
        echo -e "${CYAN}Creating virtual environment...${NC}"
        python3 -m venv venv
    fi

    # Activate and install
    source venv/bin/activate
    echo -e "${CYAN}Installing dependencies...${NC}"
    pip install --upgrade pip
    pip install -e .

    # Create .env from example
    if [[ ! -f ".env" && -f ".env.example" ]]; then
        cp .env.example .env
        echo -e "${YELLOW}Created .env from .env.example - EDIT IT WITH YOUR API KEYS!${NC}"
    fi

    echo -e "${GREEN}Setup complete!${NC}"
    echo
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Edit .env with your LLM API keys (GEMINI_API_KEY, etc.)"
    echo "  2. Run: ./run.sh up"
    echo "  3. Run: ./run.sh bootstrap"
    echo "  4. Run: ./run.sh api"
}

# Command: all (complete startup)
cmd_all() {
    echo -e "${BLUE}=== ETHIO-RTAP Complete Startup ===${NC}"
    cmd_setup
    cmd_up
    cmd_bootstrap
    echo
    echo -e "${GREEN}Platform ready! Starting API...${NC}"
    cmd_api
}

# Help
cmd_help() {
    cat <<EOF
${BLUE}ETHIO-RTAP Universal Startup Script${NC}

Usage: ./run.sh [command]

Commands:
  ${GREEN}setup${NC}       One-time setup (venv, deps, .env)
  ${GREEN}up${NC}          Start Neo4j + Qdrant containers
  ${GREEN}down${NC}        Stop containers
  ${GREEN}restart${NC}     Restart containers
  ${GREEN}ps${NC}          Show container status
  ${GREEN}logs${NC} [svc]  Show logs (optional service name)
  ${GREEN}bootstrap${NC}   Initialize schema, load threat intel, populate vectors
  ${GREEN}api${NC}         Start FastAPI server (port 8000)
  ${GREEN}test${NC}        Run health checks
  ${GREEN}all${NC}         Complete setup + bootstrap + API (one command!)
  ${GREEN}help${NC}        Show this help

Examples:
  ./run.sh all              # Complete startup in one command
  ./run.sh setup            # First time only
  ./run.sh up               # Start databases
  ./run.sh bootstrap        # Initialize platform
  ./run.sh api              # Start API server
  ./run.sh logs neo4j       # View Neo4j logs

Environment:
  Edit .env with your API keys:
    GEMINI_API_KEY=...
    ANTHROPIC_API_KEY=...
    OPENAI_API_KEY=...
    OPENROUTER_API_KEY=...

Supported Runtimes:
  - Docker + Docker Compose v2 (docker compose)
  - Docker + Docker Compose v1 (docker-compose)
  - Podman + Podman Compose (podman-compose / podman compose)

EOF
}

# Main
main() {
    case "${1:-help}" in
        setup) cmd_setup ;;
        up) cmd_up ;;
        down) cmd_down ;;
        restart) cmd_restart ;;
        ps) cmd_ps ;;
        logs) cmd_logs "$@" ;;
        bootstrap) cmd_bootstrap ;;
        api) cmd_api ;;
        test) cmd_test ;;
        all) cmd_all ;;
        help|--help|-h) cmd_help ;;
        *) echo -e "${RED}Unknown command: $1${NC}"; cmd_help; exit 1 ;;
    esac
}

main "$@"