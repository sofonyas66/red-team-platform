# ETHIO-RTAP — Red Team Planning & Analysis Platform

> **Attack path discovery, GNN risk scoring and campaign planning for Active Directory environments**
> *Graduation project — INSA Ethio Cyber Talent Program, Red Team Track*

---

## Overview

ETHIO-RTAP automates the planning phase of a red team engagement. It ingests BloodHound/SharpHound Active Directory collections, builds a graph of the environment, finds attack paths to high-value targets, scores them with a Graph Attention Network (GAT), correlates them with Ethiopian threat intelligence (ETI-Core, STIX 2.1), and generates a structured campaign plan.

It is a **planning and intelligence tool**: it recommends paths and plans, and never executes anything against a target. It is in the same category as BloodHound.

Three things set it apart:

1. **ETI-Core** — a STIX 2.1 database of threat actors and techniques relevant to Ethiopia, used to tie paths to realistic adversaries.
2. **GNN path scoring** — a GAT over the AD graph ranks candidate paths.
3. **Offline / air-gapped deployment** — the stack runs locally (Neo4j, Postgres, Qdrant, optional Ollama), with no required cloud dependency.

It is **multi-tenant**: each organization's data is isolated at every layer, so one platform can serve several customers.

---

## Team

| Member | Role | Responsibilities |
| :--- | :--- | :--- |
| **Sofonyas** (GitHub: [sofonyas66](https://github.com/sofonyas66)) | Technical Lead & Graph ML Engineer | Architecture, FastAPI backend, multi-tenant authentication, Neo4j/Postgres, attack-path discovery, GNN scoring, CLI integration |
| **Natnael** (GitHub: [natnaelCR7](https://github.com/natnaelCR7)) |  LLM & Data Ingestion Engineer | BloodHound/SharpHound ingestion, schema validation, data normalization, security data analysis, LLM context engineering, RAG pipeline, campaign-plan generation and evaluation |
| **Azariyas** (GitHub: [AC0x84](https://github.com/AC0x84)) | Threat Intelligence Engineer | ETI-Core research, STIX 2.1 data modeling, threat actor and technique mapping, intelligence correlation, source validation and documentation |

---

## Features

| Area | Status |
| :--- | :--- |
| Multi-tenant auth (JWT with org and role claims), per-org engagement isolation | ✅ Verified |
| BloodHound / SharpHound ingestion (ZIP or JSON) per engagement | ✅ Verified |
| Attack path discovery with GAT scoring | ✅ Working |
| Overview dashboard: pipeline status, relationship types, privileged accounts, ranked paths | ✅ Working |
| Deterministic risk labels (High / Medium / Low) with explained steps | ✅ Working |
| Threat actor correlation (ETI-Core) | ✅ Working |
| Campaign plan generation (CLI) | ✅ Working |
| Campaign plans in the web UI, saved per engagement | 🚧 In progress |
| Threat actors page, Settings | 🚧 Planned |

---

## How risk is labelled

Each candidate path gets a label from its structure, not from the model alone. The GAT score is shown as a secondary, relative value.

- **Structural edges** (`MemberOf`, `Contains`, `GpLink`) cost an attacker nothing and are not counted as steps.
- **Control edges** (`AdminTo`, `GenericAll`, `GenericWrite`, `WriteDacl`, `WriteOwner`, `Owns`, `AllExtendedRights`, `ForceChangePassword`, `AddMember`) give real control over the next object.

| Label | Rule |
| :--- | :--- |
| **High** | 2 or fewer steps and every step is a control edge |
| **Medium** | 3–4 steps, or 2 or fewer steps that include a non-control edge (e.g. `HasSession`, `CanRDP`) |
| **Low** | everything else |

Paths whose source account already holds privileged rights (`admincount`) are tagged **Already privileged**, since they are not real escalation.

---

## Architecture

```
┌──────────────────────┐     ┌──────────────────────────┐
│ BloodHound/SharpHound│     │ STIX 2.1 Threat Intel    │
│ AD export (.zip)     │     │ ETI-Core                 │
└──────────┬───────────┘     └────────────┬─────────────┘
           └──────────┬──────────────┬────┘
                      ▼              ▼
              ┌──────────────────────────┐        ┌──────────────┐
              │  Neo4j graph (tenant-    │        │  Postgres    │
              │  scoped by org_id +      │        │  orgs, users,│
              │  engagement_id)          │        │  engagements,│
              └────────┬─────────┬───────┘        │  plans       │
                       │         │                └──────┬───────┘
          ┌────────────┘         └──────────┐            │
          ▼                                 ▼            │
   ┌─────────────┐                    ┌─────────────┐    │
   │ Node2Vec +  │                    │   Qdrant    │    │
   │ GAT scoring │                    │ (optional   │    │
   └──────┬──────┘                    │  RAG)       │    │
          └──────────────┬────────────┴─────────────┘    │
                         ▼                               │
                ┌──────────────────┐                     │
                │   LLM planner    │◄────────────────────┘
                └────────┬─────────┘
                         ▼
          ┌──────────────────────────────┐
          │ FastAPI  ·  rtap CLI  ·  Web │
          └──────────────────────────────┘
```

### Tenant isolation

- `org_id` is taken **only from the JWT**, never from the client.
- Every graph node carries `org_id` and `engagement_id`; all Neo4j access goes through a `TenantSession` wrapper, and a CI script checks that no tenant node lacks these properties.
- Engagement access is verified on every request: a malformed ID returns `422`, another organization's engagement returns `404`.
- ETI-Core nodes (`ThreatActor`, `Technique`, `Sector`) are global by design.

### Stack

| Layer | Technology |
| :--- | :--- |
| Backend | Python, FastAPI, SQLAlchemy + Alembic |
| Graph / data | Neo4j, Postgres, Qdrant |
| ML | PyTorch (CPU), torch-geometric (GAT), Node2Vec, sentence-transformers (optional, for RAG) |
| LLM | OpenAI-compatible provider layer (hosted APIs or local Ollama) |
| Frontend | Next.js, TypeScript, pnpm |
| CLI | Typer (`rtap`) |

---

## Getting started

**Requirements:** Docker (Neo4j, Postgres, Qdrant), Python 3.14, Node.js with pnpm.

### Quick start (one-shot)

```bash
git clone <repository-url>
cd red-team-platform
./bootstrap.sh
```

The bootstrap script starts Docker services, creates a virtual environment, installs dependencies, runs migrations, seeds a test user, and optionally starts the API and frontend.

### Manual setup

```bash
git clone https://github.com/sofonyas66/red-team-platform.git
cd red-team-platform

# 1. Infrastructure
docker compose up -d

# 2. Backend environment (core and ML dependencies are split in pyproject.toml)
python -m venv .venv
# install the core dependencies, then the ML extras if you want GNN scoring

# 3. Configuration: create a .env with your database URLs, JWT secret
#    and LLM provider settings (see backend/config.py for the variables)

# 4. Database migrations
alembic upgrade head

# 5. API  (restart it after every backend change)
PYTHONPATH=backend .venv/bin/python backend/start_api.py

# 6. Web UI
cd frontend && pnpm install && pnpm dev     # http://localhost:3000
```

CLI:

```bash
./rtap --help
```

### Notes

- **Older CPUs (no AVX2):** `numpy` must be built from source with CPU dispatch disabled, and `torch` must come from the CPU-only index (`https://download.pytorch.org/whl/cpu`). Do not upgrade either casually.
- **Retrieval (RAG) is optional.** Without `sentence-transformers`, campaign plans are still generated from graph-based threat actor matching and the LLM, and the plan is marked as generated without retrieval.
- **No placeholder plans.** If the LLM provider is unreachable, plan generation returns a `503` error and saves nothing. The platform never substitutes a canned plan.
- **Risk scores** from the GAT are relative values, not probabilities.

---

## Known limitations

- The ingestor currently stores a subset of SharpHound properties (`name`, `samaccountname`, `enabled`, `admincount`, `description`, `operatingsystem`). Findings that need `hasspn`, `dontreqpreauth` or `unconstraineddelegation` are future work.
- GAT scoring is trained per engagement on a small graph; use scores to rank paths, not as absolute risk.

---

## Security notice

This platform is intended exclusively for **authorized cybersecurity research** and red team planning. Obtain permission before modelling any production environment.
