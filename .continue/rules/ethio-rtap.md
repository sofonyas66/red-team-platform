---
name: ETHIO-RTAP rules
description: Shared rules for every agent on this project
alwaysApply: true
---
# Repository Overview

## Project Description
ETHIO-RTAP is an enterprise-grade red team planning platform that models Active Directory environments, discovers lateral movement attack paths, scores traversal risk using Graph Neural Networks (GNN), correlates paths with real-world threat actors, and generates actionable campaign playbooks using Large Language Models (LLMs).

**Main purpose and goals:**
- Import BloodHound/SharpHound AD exports (.zip files) into Neo4j graph database
- Discover and score attack paths using Graph Neural Networks (PathGAT)
- Correlate attack techniques with threat actor profiles from STIX 2.1 threat intelligence
- Generate detailed campaign playbooks using LLMs (OpenAI, Gemini, Anthropic, etc.)
- Provide web-based dashboard for security teams to visualize and analyze attack surfaces
- Support multi-tenant architecture with organization and engagement scoping

**Key technologies used:**
- **Backend:** Python 3.10+, FastAPI, Neo4j (graph database), SQLAlchemy/PostgreSQL (metadata)
- **ML/AI:** PyTorch, Torch-Geometric (GNN PathGAT), Sentence Transformers (RAG), Node2Vec (embeddings)
- **Vector Database:** Qdrant (for threat intelligence retrieval)
- **Frontend:** Next.js 16.4.0, React, TypeScript, Tailwind CSS, shadcn/ui components
- **Infrastructure:** Docker Compose (Neo4j, PostgreSQL), Makefile for orchestration
- **Authentication:** JWT-based auth with bcrypt password hashing
- **API Documentation:** Auto-generated OpenAPI/Swagger docs

## Architecture Overview

### High-level Architecture
```
┌──────────────────────┐     ┌──────────────────────────┐
│ BloodHound/SharpHound│     │ STIX 2.1 Threat Intel    │
│ AD Export (.zip)      │     │ Bundles (eti_core/)      │
└──────────┬───────────┘     └────────────┬─────────────┘
           │                              │
           └──────────┬──────────────┬────┘
                      ▼              ▼
              ┌──────────────────────────┐
              │       Neo4j Graph        │
              └────────┬─────────┬───────┘
                       │         │
          ┌────────────┘         └────────────┐
          ▼                                   ▼
   ┌─────────────┐                     ┌─────────────┐
   │  Node2Vec   │                     │   Qdrant    │
   │  GNN Model  │                     │ Vector DB   │
   └──────┬──────┘                     └──────┬──────┘
          │                                   │
          └────────────┬──────────────────────┘
                       ▼
              ┌──────────────────┐
              │   LLM Planner    │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  rtap CLI / API  │
              └──────────────────┘
                      ▲
                      ▼
              ┌──────────────────┐
              │   Next.js Web    │
              │   Dashboard      │
              └──────────────────┘
```

### Main Components and Their Relationships

1. **Data Ingestion Layer (`etl/bloodhound.py`):**
   - Processes BloodHound JSON exports from SharpHound
   - Maps AD objects to Neo4j nodes and relationships
   - Scopes data to organization and engagement IDs
   - Handles deduplication and incremental ingestion

2. **Graph Database Layer (`graph/`, `db/`):**
   - Neo4j stores the AD graph structure (Users, Computers, Groups, GPOs, etc.)
   - PostgreSQL stores metadata (users, orgs, engagements, ingestion records)
   - Tenant-scoped queries ensure data isolation between organizations

3. **Machine Learning Layer (`gnn/`, `llm/`):**
   - **GNN (`gnn/init_gat.py`, `gnn/model.py`):** PathGAT model for scoring attack paths
   - **Embeddings (`gnn/embeddings.py`):** Node2Vec embeddings for graph nodes
   - **RAG (`llm/rag.py`):** Retrieval-Augmented Generation using Qdrant + Sentence Transformers
   - **Planner (`llm/planner.py`):** Combines GNN scoring, RAG context, and LLM generation

4. **API Layer (`api/`):**
   - FastAPI endpoints for all platform functionality
   - Authentication and role-based access control
   - Background task handling for long-running operations

5. **Frontend Layer (`frontend/`):** 
   - Next.js dashboard for visualizing attack surfaces, paths, and campaigns
   - Real-time statistics and activity feeds
   - Engagement and workspace management

### Data Flow and System Interactions
1. **Ingestion Flow:** BloodHound ZIP → etl/bloodhound.py → Neo4j (nodes/rels) + PostgreSQL (metadata)
2. **Embedding Flow:** Neo4j graph → gnn/embeddings.py (Node2Vec) → gnn/init_gat.py (tensor creation)
3. **Training Flow:** gnn/init_gat.py → gnn/model.py (PathGAT training) → cached model files
4. **Query Flow:** User request → API endpoint → graph/tenant_session.py (scoped Neo4j queries) 
5. **Path Scoring:** llm/planner.py → gnn/init_gat.py (get_gat_state/score_candidate_path) 
6. **Campaign Generation:** llm/planner.py → llm/rag.py (context retrieval) → LLM provider (text generation)
7. **Dashboard:** frontend/ → API calls → React components → Charts/tables

## Directory Structure

### Important Directories and Their Purposes

```
/ (root)
├── AGENTS.md                 ← This file
├── .continue/                ← AI agent custom commands (to be created)
├── backend/                  ← Python/FastAPI backend
│   ├── api/                  ← FastAPI endpoints and middleware
│   ├── db/                   │   # Database models and connection
│   ├── gnn/                  │   # Graph Neural Network components
│   ├── graph/                │   # Neo4j connection and querying
│   ├── llm/                  │   # LLM planner, RAG, provider
│   ├── etl/                  │   # Data ingestion (BloodHound)
│   ├── eti_core/             │   # Threat intelligence (STIX bundles)
│   ├── cli/                  │   # Command-line interface
│   ├── migrations/           │   # Alembic database migrations
│   ├── scripts/              │   # Helper scripts
│   ├── config.py             │   # Central configuration
│   ├── bootstrap.py          │   # Platform initialization
│   ├── run.sh                │   # Main entry point
│   ├── Makefile              │   # Development commands
│   ├── pyproject.toml        │   # Python dependencies
│   └── requirements-lock.txt │   # Frozen dependencies
├── frontend/                 ← Next.js/Tailwind frontend
│   ├── app/                  ← App router (pages, layouts)
│   ├── components/           ← Reusable UI components
│   ├── lib/                  ← Custom hooks and utilities
│   ├── public/               ← Static assets
│   ├── package.json          ← NPM dependencies
│   ├── next.config.mjs       ← Next.js configuration
│   └── tsconfig.json         ← TypeScript configuration
├── docker-compose.yml        ← Container orchestration
├── .env.example              ← Environment variable template
├── ethio-rtap-status.md      ← Deployment status document
├── postman/                  ← API testing collection
├── public/                   ← Static files served by backend
└── rtap                      ← CLI entry point
```

### Key Files and Configuration
- **`pyproject.toml`**: Core Python dependencies + optional ML dependencies (torch, torch-geometric, etc.)
- **`requirements-lock.txt`**: Frozen dependency versions for reproducible builds
- **`docker-compose.yml`**: Defines Neo4j, PostgreSQL, and backend/frontend services
- **`.env.example`**: Template for environment variables (API keys, DB URLs, secrets)
- **`Makefile`**: Development shortcuts (install, bootstrap, api, test, clean, up)
- **`bootstrap.py`**: One-click setup for databases, threat intel, embeddings
- **`config.py`**: Centralized configuration loading from environment variables
- **`alembic.ini`**: Database migration configuration

### Entry Points and Main Modules
- **Backend API:** `backend/start_api.py` → launches `uvicorn api.main:app`
- **CLI Interface:** `backend/cli/main.py` → `rtap` command (via pyproject.toml entry point)
- **Bootstrap Script:** `backend/bootstrap.py` → runs `make bootstrap`
- **Frontend Dev Server:** `pnpm --frontend run dev` (via package.json scripts)
- **Frontend Build:** `pnpm --frontend run build` (for production)

## Development Workflow

### How to Build/Run the Project

1. **Initial Setup:**
   ```bash
   # Clone repository and navigate to directory
   git clone <repository-url>
   cd red-team-platform
   
   # Set up Python virtual environment and install dependencies
   make install
   ```

2. **Configuration:**
   ```bash
   # Edit environment variables (API keys for LLMs, etc.)
   nano .env
   # Required: At least one LLM provider key (OPENAI_API_KEY, GEMINI_API_KEY, etc.)
   ```

3. **Platform Initialization:**
   ```bash
   # Start databases, load threat intelligence, initialize embeddings
   make bootstrap
   ```

4. **Start Services:**
   ```bash
   # Start the FastAPI backend server
   make api
   
   # In another terminal, start the frontend development server
   cd frontend && pnpm dev
   ```
   
   Or start both with Docker Compose:
   ```bash
   docker compose up
   ```

5. **Access the Platform:**
   - API: http://localhost:8000 (docs at http://localhost:8000/docs)
   - Frontend: http://localhost:3000
   - Login: Use credentials from `seed_test_user.py` or create your own

### Testing Approach
- **Backend Tests:** Located in respective test files or invoked via `make test`
- **Health Checks:** API endpoints like `/health`, `/graph/stats` verify service availability
- **Unit Tests:** Individual components tested in isolation (where implemented)
- **Integration Tests:** End-to-end flows tested via manual QA or automated scripts
- **ML Model Testing:** GNN scoring validated against known paths in test data

### Development Environment Setup
1. **Prerequisites:**
   - Docker & Docker Compose (or Podman)
   - Python 3.10+ 
   - Node.js 18+ and pnpm
   - Git

2. **Recommended Setup:**
   ```bash
   # Fork/clone the repository
   git clone <your-fork-url>
   cd red-team-platform
   
   # Install pre-commit hooks (if available)
   pip install pre-commit
   pre-commit install
   
   # Set up development environment
   make install  # Creates .venv and installs Python deps
   cd frontend && pnpm install  # Installs Node.js deps
   ```

### Lint and Format Commands
- **Python Linting/Formatting:** 
  ```bash
  # Using project's existing tools (ruff/black if configured)
  make lint        # If defined in Makefile
  # Or manually:
  pip install ruff black
  ruff check backend/
  black backend/
  ```
  
- **TypeScript/JavaScript Linting/Formatting:**
  ```bash
  # Using Next.js built-in tools
  cd frontend
  pnpm lint        # If defined in package.json
  pnpm format      # If defined in package.json
  # Or manually with:
  pnpm add -D eslint prettier
  pnpm eslint . --ext .ts,.tsx
  pnpm prettier --write .
  ```

- **Dependency Security Scanning:**
  ```bash
  # Python dependencies
  pip install safety
  safety check
  
  # Node.js dependencies  
  cd frontend && pnpm audit
  ```

## Additional Notes

### Environment Variables
Key variables in `.env` file:
- `DATABASE_URL`: PostgreSQL connection string
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`: Neo4j connection
- `JWT_SECRET_KEY`: For signing authentication tokens
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`: LLM provider configuration
- `ALLOWED_ORIGINS`: CORS origins for frontend

### Multi-tenancy Design
- Data is scoped by `organization_id` and `engagement_id` 
- All Neo4j queries include `$org_id` and/or `$engagement_id` parameters
- PostgreSQL uses row-level security implicitly through querying
- API endpoints validate that resources belong to the user's organization

### Extensibility Points
1. **Add new threat intelligence:** Place STIX 2.1 bundles in `backend/eti_core/`
2. **Custom LLM providers:** Extend `backend/llm/provider.py`
3. **Alternative GNN models:** Modify `backend/gnn/model.py`
4. **New API endpoints:** Add to `backend/api/main.py` or create new modules
5. **Frontend components:** Add to `frontend/components/` or `frontend/app/`

### Production Considerations
- Use reverse proxy (NGINX/Traefik) for SSL termination
- Configure proper secrets management (Vault, AWS Secrets Manager, etc.)
- Set up monitoring and logging (ELK stack, Prometheus/Grafana)
- Implement rate limiting and DDoS protection
- Regular backup strategies for Neo4j and PostgreSQL