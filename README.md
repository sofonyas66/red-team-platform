# ETHIO-RTAP — Red Team Planning & Analysis Platform

> **AI-Powered Attack Path Discovery, GNN Risk Scoring & Campaign Generation**
>
> *Developed for the INSA Ethio Cyber Talent Program — Red Team Track*

---

## Overview

ETHIO-RTAP is an enterprise-grade red team planning platform that models Active Directory environments, discovers lateral movement attack paths, scores traversal risk using Graph Neural Networks, correlates paths with real-world threat actors, and generates actionable campaign playbooks using LLMs.

The platform combines:
- **Neo4j** — Knowledge graph database for AD topology and threat intelligence
- **Qdrant** — Vector store for semantic threat intelligence retrieval (RAG)
- **PyTorch Geometric** — Node2Vec structural embeddings for GNN-based risk scoring
- **LLM Integration** — Campaign plan generation via Gemini, OpenAI, Anthropic, or local Ollama

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Docker** and **Docker Compose**
- At least one LLM API key (Gemini, OpenAI, Anthropic, or OpenRouter) — *or* a local Ollama instance

### 1. Clone & Install

```bash
git clone <repository-url>
cd red-team-platform

python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 2. Configure Environment

Create or update the `.env` file in the project root:

```env
# LLM Provider: "api" (cloud) or "ollama" (local)
LLM_PROVIDER=api

# Set at least one API key if using cloud LLMs
GEMINI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here

# Database connections (defaults work with docker-compose)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 3. Bootstrap the Platform

Start databases, initialize the schema, load threat intelligence, and populate the vector store — all in one command:

```bash
docker compose up -d        # Start Neo4j + Qdrant containers
python bootstrap.py         # Initialize everything
```

### 4. Ingest Your Active Directory Data

Upload a BloodHound/SharpHound `.zip` export:

```bash
rtap auth login --username admin
rtap ingest bloodhound <path/to/sharphound_export.zip>
```

### 5. Train GNN Embeddings

Generate Node2Vec structural embeddings for risk scoring:

```bash
python -m gnn.embeddings
```

### 6. Start the API Server

```bash
python start_api.py
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 7. Use the CLI

```bash
rtap paths "USER@DOMAIN.LOCAL" "TARGET_COMPUTER.DOMAIN.LOCAL"
rtap plan generate "USER@DOMAIN.LOCAL" "TARGET_COMPUTER.DOMAIN.LOCAL"
```

---

## Architecture

```
┌──────────────────────┐     ┌──────────────────────────┐
│ BloodHound/SharpHound│     │ STIX 2.1 Threat Intel    │
│ AD Export (.zip)      │     │ Bundles (eti_core/)      │
└──────────┬───────────┘     └────────────┬─────────────┘
           │                              │
           │  etl/bloodhound.py           │  eti_core/loader.py
           └──────────┬──────────────┬────┘
                      │              │
                      ▼              ▼
              ┌──────────────────────────┐
              │       Neo4j Graph        │
              │  (Users, Groups, Comps,  │
              │   Actors, Techniques)    │
              └────────┬─────────┬───────┘
                       │         │
          ┌────────────┘         └────────────┐
          ▼                                   ▼
   ┌─────────────┐                     ┌─────────────┐
   │  Node2Vec   │                     │   Qdrant    │
   │  GNN Model  │                     │ Vector DB   │
   │  (PyG)      │                     │ (RAG)       │
   └──────┬──────┘                     └──────┬──────┘
          │                                   │
          └────────────┬──────────────────────┘
                       ▼
              ┌──────────────────┐
              │   LLM Planner    │
              │  (Campaign Gen)  │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  rtap CLI / API  │
              └──────────────────┘
```

### Pipeline Steps

| Step | Component | Description |
|------|-----------|-------------|
| 1 | **Graph Ingestion** | Merges AD topology with STIX 2.1 threat actors/techniques into Neo4j |
| 2 | **GNN Training** | Node2Vec generates 128-dim structural embeddings for every graph node |
| 3 | **Path Scoring** | Discovers attack paths and scores each hop using GNN embedding similarity |
| 4 | **Threat Intel RAG** | Retrieves relevant threat actor context from Qdrant via semantic search |
| 5 | **Campaign Planning** | LLM synthesizes paths + threat intel into an actionable campaign playbook |

---

## Project Structure

```
red-team-platform/
├── api/                    # FastAPI REST backend
│   ├── main.py             #   Endpoint definitions
│   └── auth.py             #   JWT authentication
│
├── cli/                    # rtap CLI client
│   └── main.py             #   Typer command definitions
│
├── eti_core/               # Threat Intelligence module
│   ├── loader.py           #   STIX 2.1 parser & Neo4j ingester
│   └── actors/             #   Threat actor JSON bundles
│       ├── financial.json
│       └── state_affiliated.json
│
├── etl/                    # Data ingestion pipelines
│   └── bloodhound.py       #   SharpHound ZIP → Neo4j
│
├── gnn/                    # Graph Neural Network layer
│   ├── embeddings.py       #   Node2Vec embedding generator
│   └── init_gat.py         #   PathGAT model initialization
│
├── graph/                  # Graph database layer
│   ├── connection.py       #   Neo4j driver setup
│   └── schema.py           #   Constraints & indexes
│
├── llm/                    # LLM reasoning layer
│   ├── provider.py         #   Multi-provider LLM client
│   ├── rag.py              #   Qdrant vector store & retrieval
│   └── planner.py          #   Campaign plan orchestration
│
├── data/                   # Runtime data
│   └── ingestion_log.json  #   Deduplication hash log
│
├── bootstrap.py            # One-command platform initializer
├── start_api.py            # API server launcher
├── rtap                    # CLI wrapper script
├── pyproject.toml          # Package configuration & entry points
├── docker-compose.yml      # Neo4j + Qdrant containers
├── requirements.txt        # Python dependencies
└── .env                    # Environment configuration
```

---

## `rtap` CLI Reference

The `rtap` command is the primary interface for interacting with the platform. Use `rtap <command> --help` for detailed usage on any command.

### Authentication

```bash
# Log in (token cached at ~/.rtap/token.json with 0600 permissions)
rtap auth login --username admin

# Check current session
rtap auth whoami

# Log out (clears cached token)
rtap auth logout
```

### Graph Inspection

```bash
# Display node and relationship counts
rtap graph stats
```

### Threat Actors

```bash
# List known threat actor profiles
rtap actors list

# Show full technique names
rtap actors list --verbose
```

### Active Directory Ingestion

```bash
# Upload a SharpHound/BloodHound .zip export
rtap ingest bloodhound <path/to/export.zip>
```

The ingest command:
- Validates the file exists and is a `.zip`
- Uploads via multipart POST to the API
- Deduplicates previously ingested files by SHA-256 hash
- Displays node/relationship count tables
- Warns about skipped ACE types and incomplete collections

### Attack Path Discovery

```bash
# Find and score attack paths between two AD nodes
rtap paths "SOURCE_USER@DOMAIN.LOCAL" "TARGET_COMPUTER.DOMAIN.LOCAL"
```

Output includes:
- **Rank** — Path priority (1 = highest risk)
- **Risk** — Color-coded severity (HIGH 🔴 / MEDIUM 🟡 / LOW)
- **GAT Score** — GNN-derived traversal risk score
- **Hops** — Number of edges in the path
- **Path** — Full traversal chain with relationship types

### Campaign Plan Generation

```bash
# Generate an AI-powered red team campaign playbook
rtap plan generate "SOURCE_USER@DOMAIN.LOCAL" "TARGET_COMPUTER.DOMAIN.LOCAL"
```

This command:
1. Discovers the highest-risk attack path
2. Correlates it with a matching threat actor profile
3. Retrieves relevant threat intelligence from Qdrant
4. Generates a comprehensive campaign plan via LLM

---

## API Endpoints

The FastAPI backend runs on `http://localhost:8000`. Full interactive documentation available at `/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | System health check (no auth required) |
| `POST` | `/auth/login` | Obtain JWT token |
| `GET` | `/graph/stats` | Node and relationship counts |
| `GET` | `/actors` | List threat actor profiles |
| `POST` | `/ingest/bloodhound` | Upload SharpHound ZIP |
| `GET` | `/paths?source=...&target=...` | Discover scored attack paths |
| `POST` | `/plan/generate` | Generate campaign playbook |

All endpoints except `/health` and `/auth/login` require a valid JWT token via `Authorization: Bearer <token>` header.

---

## Database Access

### Neo4j Browser

Access the graph database directly at `http://localhost:7474` (credentials: `neo4j` / `changeme`).

**Useful Cypher Queries:**

```cypher
-- Count nodes by label
MATCH (n) RETURN labels(n)[0] AS Label, count(n) AS Count ORDER BY Count DESC

-- View threat actors and their techniques
MATCH (a:ThreatActor)-[:USES]->(t:Technique) RETURN a.name, t.name

-- Find shortest paths from a user to a target
MATCH p = shortestPath((u:User {name: $source})-[*1..5]->(t:Computer {name: $target}))
RETURN p LIMIT 10

-- List nodes with GNN embeddings
MATCH (n) WHERE n.embedding IS NOT NULL
RETURN labels(n)[0] AS Type, n.name AS Name, size(n.embedding) AS Dimensions LIMIT 10
```

### Qdrant Dashboard

Access the vector database dashboard at `http://localhost:6333/dashboard`.

---

## Operational Workflow

A typical red team assessment workflow:

```
1. Bootstrap        →  python bootstrap.py
2. Start API        →  python start_api.py
3. Authenticate     →  rtap auth login --username admin
4. Ingest AD Data   →  rtap ingest bloodhound <sharphound.zip>
5. Train GNN        →  python -m gnn.embeddings
6. Discover Paths   →  rtap paths "user@domain" "target.domain"
7. Generate Plan    →  rtap plan generate "user@domain" "target.domain"
```

---

## Security Notice

This platform is designed exclusively for **authorized cybersecurity research**, red team emulation exercises, and security planning. Obtain proper authorization before scanning or modeling production networks.

---

## License & Credits

- **Project**: Red Team Planning and Analysis Platform (ETHIO-RTAP)
- **Affiliation**: INSA Ethio Cyber Talent Program — Red Team Track
