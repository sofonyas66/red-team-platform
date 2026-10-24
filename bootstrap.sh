#!/usr/bin/env bash
# =============================================================================
# ETHIO-RTAP — Smart Bootstrap Script
# One-shot setup for a fresh clone: Docker, venv, config, migrations, seed user.
# Safe to re-run; skips steps that are already done.
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

log()  { echo -e "${BLUE}[bootstrap]${NC} $*"; }
ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[err]${NC} $*"; }

# -----------------------------------------------------------------------------
# 0. Prerequisites check
# -----------------------------------------------------------------------------
log "Checking prerequisites..."

for cmd in docker python3 pnpm; do
    if ! command -v "$cmd" &>/dev/null; then
        err "Missing: $cmd — please install it first"
        exit 1
    fi
done

# Docker daemon running?
if ! docker info &>/dev/null; then
    err "Docker daemon not running. Start Docker Desktop / docker service."
    exit 1
fi

# Python version (need 3.11+ for torch CPU wheels)
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$(printf '%s\n' "3.11" "$PY_VER" | sort -V | head -1)" != "3.11" ]]; then
    warn "Python $PY_VER detected; 3.11+ recommended for torch CPU wheels"
fi

ok "Prerequisites satisfied"

# -----------------------------------------------------------------------------
# 1. Docker Compose — start infrastructure
# -----------------------------------------------------------------------------
log "Starting Docker services (Postgres, Neo4j, Qdrant)..."
docker compose up -d

# Wait for services to be healthy
log "Waiting for services to be ready..."
for svc in postgres neo4j qdrant; do
    log "  Waiting for $svc..."
    for i in {1..30}; do
        if docker compose ps "$svc" | grep -q "healthy\|Up"; then
            ok "$svc is up"
            break
        fi
        sleep 2
    done
done

# -----------------------------------------------------------------------------
# 2. Environment file (.env) — interactive if missing
# -----------------------------------------------------------------------------
ENV_FILE="$REPO_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    log "No .env found — creating interactively"
    cp "$REPO_ROOT/.env.example" "$ENV_FILE"

    # JWT_SECRET_KEY
    if grep -q '^JWT_SECRET_KEY=$' "$ENV_FILE"; then
        read -rp "JWT_SECRET_KEY (press Enter to auto-generate for dev): " jwt_key
        if [[ -z "$jwt_key" ]]; then
            jwt_key=$(openssl rand -base64 48 | tr -d '\n')
            log "Generated JWT_SECRET_KEY"
        fi
        sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$jwt_key|" "$ENV_FILE"
    fi

    # RTAP_ADMIN_PW
    read -rsp "Password for test-admin@example.com (RTAP_ADMIN_PW): " admin_pw
    echo
    if [[ -z "$admin_pw" ]]; then
        err "RTAP_ADMIN_PW cannot be empty"
        exit 1
    fi
    # Don't write to .env — pass via env var to seed script

    # LLM (optional)
    read -rp "LLM provider URL (e.g. http://localhost:11434/v1 for Ollama, or OpenAI-compatible). Press Enter to skip: " llm_url
    if [[ -n "$llm_url" ]]; then
        read -rp "LLM_API_KEY (can be dummy for local Ollama): " llm_key
        read -rp "LLM_MODEL_NAME (e.g. llama3.1, gpt-4o-mini, or 'auto:fast'): " llm_model
        sed -i "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$llm_url|" "$ENV_FILE"
        sed -i "s|^LLM_API_KEY=.*|LLM_API_KEY=$llm_key|" "$ENV_FILE"
        sed -i "s|^LLM_MODEL_NAME=.*|LLM_MODEL_NAME=$llm_model|" "$ENV_FILE"
    fi

    ok ".env written to $ENV_FILE"
else
    ok ".env already exists — skipping interactive setup"
fi

# -----------------------------------------------------------------------------
# 3. Python virtual environment + dependencies
# -----------------------------------------------------------------------------
VENV_DIR="$REPO_ROOT/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment at .venv..."
    python3 -m venv "$VENV_DIR"
    ok "Virtual environment created"
else
    ok "Virtual environment already exists"
fi

# Activate venv for subsequent commands
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# Upgrade pip
log "Upgrading pip..."
pip install --upgrade pip -q

# Core dependencies (from requirements.txt)
log "Installing core dependencies..."
pip install -r "$REPO_ROOT/backend/requirements.txt" -q

# ML extras (torch-geometric, sentence-transformers) — optional
if [[ "${INSTALL_ML:-}" != "1" ]]; then
    read -rp "Install ML extras (torch-geometric, sentence-transformers) for GAT scoring? [y/N]: " install_ml
    if [[ "$install_ml" =~ ^[Yy]$ ]]; then
        INSTALL_ML=1
    fi
fi

if [[ "${INSTALL_ML:-}" == "1" ]]; then
    log "Installing ML extras (this may take a few minutes)..."
    # torch-geometric deps (CPU, no AVX2)
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu -q
    pip install torch-geometric torch-scatter torch-sparse torch-cluster torch-spline-conv -f https://data.pyg.org/whl/torch-2.4.0+cpu.html -q
    pip install sentence-transformers -q
    ok "ML extras installed"
else
    warn "Skipping ML extras — GAT scoring will not work without them"
fi

# -----------------------------------------------------------------------------
# 4. Database migrations (Alembic)
# -----------------------------------------------------------------------------
log "Running database migrations (alembic upgrade head)..."
cd "$REPO_ROOT/backend"
PYTHONPATH="$REPO_ROOT/backend" alembic upgrade head
ok "Migrations applied"

# -----------------------------------------------------------------------------
# 5. Seed test user
# -----------------------------------------------------------------------------
log "Seeding test user (test-admin@example.com)..."
RTAP_ADMIN_PW="$admin_pw" PYTHONPATH="$REPO_ROOT/backend" python seed_test_user.py
ok "Test user created/updated"

# -----------------------------------------------------------------------------
# 6. Offer to start services
# -----------------------------------------------------------------------------
echo
echo "============================================================================="
echo "Setup complete! You can now start the API and/or frontend."
echo "============================================================================="
echo

read -rp "Start FastAPI backend now? [Y/n]: " start_api
if [[ ! "$start_api" =~ ^[Nn]$ ]]; then
    log "Starting FastAPI on http://localhost:8000 (Ctrl+C to stop)..."
    cd "$REPO_ROOT"
    PYTHONPATH="$REPO_ROOT/backend" python backend/start_api.py &
    API_PID=$!
    sleep 2
    ok "API started (PID $API_PID)"
fi

read -rp "Start Next.js frontend dev server? [Y/n]: " start_fe
if [[ ! "$start_fe" =~ ^[Nn]$ ]]; then
    log "Starting frontend on http://localhost:3000 (Ctrl+C to stop)..."
    cd "$REPO_ROOT/frontend"
    pnpm install -q
    pnpm dev &
    FE_PID=$!
    sleep 3
    ok "Frontend started (PID $FE_PID)"
fi

# If both started, wait for user to stop
if [[ ! "$start_api" =~ ^[Nn]$ ]] || [[ ! "$start_fe" =~ ^[Nn]$ ]]; then
    echo
    log "Both services running. Press Ctrl+C to stop them."
    trap "kill ${API_PID:-} ${FE_PID:-} 2>/dev/null; exit 0" INT TERM
    wait
fi

echo
log "Done. Next time, just run:"
echo "  docker compose up -d"
echo "  source .venv/bin/activate"
echo "  PYTHONPATH=backend python backend/start_api.py"
echo "  cd frontend && pnpm dev"