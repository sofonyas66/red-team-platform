# Red Team Planning and Analysis Platform — Project Blueprint

## Directory Structure

```
red-team-platform/
│
├── graph/                          ✓ BUILT
│   ├── __init__.py
│   ├── connection.py               ✓ Neo4j driver — Bolt connection, verified
│   └── schema.py                   ✓ 9 node types, 9 constraints, 4 indexes
│
├── eti_core/                       ✓ BUILT
│   ├── __init__.py
│   ├── loader.py                   ✓ STIX 2.1 → Neo4j ingestion pipeline
│   └── actors/
│       ├── state_affiliated.json   ✓ Cyber_Horus bundle (4 techniques, 2 sectors)
│       └── financial.json          ✓ ETH-BEC-Cluster bundle (3 techniques, 1 sector)
│
├── etl/                            → NEXT
│   ├── __init__.py
│   └── bloodhound.py               → BloodHound JSON → Neo4j ingestion
│
├── gnn/                            → NEXT
│   ├── __init__.py
│   ├── embeddings.py               → Node2Vec — graph → node embeddings
│   └── model.py                    → GAT — attack path scoring
│
├── llm/                            → NEXT
│   ├── __init__.py
│   ├── rag.py                      → Qdrant — embed + store + retrieve TI chunks
│   └── planner.py                  → Ollama — campaign plan generation
│
├── api/                            → NEXT
│   ├── __init__.py
│   └── main.py                     → FastAPI — exposes all components as endpoints
│
├── data/
│   └── sample/
│       └── bloodhound_sample.json  → Sample AD data for testing (ETHBANK.LOCAL)
│
├── docker-compose.yml              → Full stack: Neo4j + Qdrant + Ollama + API
├── requirements.txt                → Python dependencies
└── README.md                       → Setup and run instructions
```

---

## Node Types in Neo4j

| Node | Source | Key Properties |
|---|---|---|
| User | BloodHound | objectid, name, enabled, admincount |
| Computer | BloodHound | objectid, name, operatingsystem |
| Group | BloodHound | objectid, name, admincount |
| Domain | BloodHound | objectid, name, functionallevel |
| GPO | BloodHound | objectid, name |
| OU | BloodHound | objectid, name, blocksinheritance |
| ThreatActor | ETI-Core | actor_id, name, sophistication, motivation |
| Technique | ETI-Core | technique_id, name, tactic |
| Sector | ETI-Core | name |

## Relationship Types

| Relationship | Between | Source |
|---|---|---|
| MemberOf | User/Computer → Group | BloodHound |
| AdminTo | User/Computer → Computer | BloodHound |
| HasSession | Computer → User | BloodHound |
| GenericAll | Any → Any | BloodHound |
| GenericWrite | Any → Any | BloodHound |
| WriteDacl | Any → Any | BloodHound |
| Contains | Domain/OU → Any | BloodHound |
| GpLink | GPO → OU/Domain | BloodHound |
| USES | ThreatActor → Technique | ETI-Core |
| TARGETS | ThreatActor → Sector | ETI-Core |

---

## Data Flow

```
BloodHound JSON          STIX 2.1 bundles
      │                        │
      ▼                        ▼
  etl/bloodhound.py      eti_core/loader.py
      │                        │
      └──────────┬─────────────┘
                 ▼
           Neo4j graph
         (graph/schema.py)
                 │
         ┌───────┴───────┐
         ▼               ▼
  gnn/embeddings.py    llm/rag.py
  (Node2Vec)           (Qdrant)
         │               │
         ▼               │
   gnn/model.py          │
   (GAT scoring)         │
         │               │
         └───────┬───────┘
                 ▼
          llm/planner.py
          (Ollama LLM)
                 │
                 ▼
         api/main.py
         (FastAPI endpoints)
                 │
                 ▼
         Campaign Plan Output
```

---

## Build Order

### Phase 1 — Foundation ✓ Done
```
graph/connection.py     → connect Python to Neo4j
graph/schema.py         → create node types + constraints
eti_core/actors/*.json  → write STIX bundles
eti_core/loader.py      → load STIX into graph
```

### Phase 2 — BloodHound Ingestion → Next
```
data/sample/bloodhound_sample.json   → create test AD environment
etl/bloodhound.py                    → parse JSON, MERGE into graph
```
Target: run `python etl/bloodhound.py data/sample/bloodhound_sample.json`
and see AD nodes + ETI-Core nodes in the same graph.

### Phase 3 — GNN
```
gnn/embeddings.py    → Node2Vec on the knowledge graph
gnn/model.py         → GAT: score attack paths by probability
```
Input: Neo4j graph
Output: ranked list of attack paths with probability scores

### Phase 4 — LLM Reasoning
```
llm/rag.py       → embed ETI-Core + ATT&CK data into Qdrant
llm/planner.py   → query Qdrant + pass context to Ollama → campaign plan
```
Input: GNN-ranked paths + threat actor context
Output: structured campaign plan text

### Phase 5 — API + Integration
```
api/main.py   → FastAPI endpoints wiring everything together
docker-compose.yml   → single command to run full stack
```

---

## What Each File Does (Full Description)

### `graph/connection.py`
Single Neo4j driver instance. Everything else imports `driver` from here.
```python
from graph.connection import driver
```

### `graph/schema.py`
Creates all constraints and indexes on first run. Safe to re-run (uses IF NOT EXISTS).
```bash
python graph/schema.py
```

### `eti_core/loader.py`
Reads every `.json` file in `eti_core/actors/`, parses STIX bundles, and
MERGEs threat actors, techniques, sectors, and their relationships into Neo4j.
Safe to re-run (idempotent MERGE operations).
```bash
python eti_core/loader.py
```

### `etl/bloodhound.py` (to build)
Accepts a BloodHound JSON export path, parses each object type
(users, computers, groups, domains, GPOs, OUs), and MERGEs them into
Neo4j with `source: 'bloodhound'` property to distinguish from ETI-Core data.
```bash
python etl/bloodhound.py data/sample/bloodhound_sample.json
```

### `gnn/embeddings.py` (to build)
Pulls the graph from Neo4j into a NetworkX/PyG format, runs Node2Vec
to generate 128-dim embeddings for every node, stores embeddings back
as node properties in Neo4j.
```bash
python gnn/embeddings.py
```

### `gnn/model.py` (to build)
Graph Attention Network. Takes node embeddings + edge features,
scores candidate paths from a given source node to a target (e.g. Domain Admin),
returns top-N paths with probability scores.
```python
from gnn.model import score_paths
paths = score_paths(source_id="user--hr01", target_label="Domain Admin", top_n=5)
```

### `llm/rag.py` (to build)
Embeds ETI-Core threat actor profiles and ATT&CK technique descriptions
into Qdrant vector store. On query, retrieves the most relevant chunks
for a given set of attack paths and target sector.
```python
from llm.rag import retrieve_context
context = retrieve_context(paths=paths, sector="government")
```

### `llm/planner.py` (to build)
Takes GNN-ranked paths + RAG context and sends a structured prompt to
Ollama (Llama 3.1). Returns a campaign plan with phases, techniques,
detection hypotheses, and threat actor attribution.
```python
from llm.planner import generate_plan
plan = generate_plan(paths=paths, context=context)
```

### `api/main.py` (to build)
FastAPI app with these endpoints:
```
POST /ingest/bloodhound     → upload BloodHound JSON, ingest to graph
POST /ingest/stix           → upload STIX bundle, load to ETI-Core
GET  /graph/paths           → run GNN, return top attack paths
POST /plan/generate         → run full pipeline, return campaign plan
GET  /actors                → list threat actors in ETI-Core
GET  /health                → stack health check
```

---

## docker-compose.yml (target)

```yaml
version: "3.9"
services:
  neo4j:
    image: neo4j:latest
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: neo4j/changeme
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    restart: unless-stopped

  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - neo4j
      - qdrant
      - ollama
    restart: unless-stopped
```

Start everything:
```bash
docker compose up -d
```

---

## Requirements

```
neo4j==6.2.0
stix2==3.0.2
torch==2.12.1+cpu         # CPU-only build
torch-geometric==2.8.0
node2vec==0.5.0
fastapi==0.138.1
uvicorn==0.49.0
qdrant-client
ollama
networkx
numpy
```

Install:
```bash
pip install -r requirements.txt
```

---

## Current Graph State

```
Nodes: 12
  ThreatActor (2)  →  Cyber_Horus, ETH-BEC-Cluster
  Technique   (7)  →  T1566.001, T1078.002, T1059.001, T1071.001,
                       T1566.002, T1114.002, T1036
  Sector      (3)  →  government, energy, financial

Relationships: 10
  USES    (7)  →  actor → technique
  TARGETS (3)  →  actor → sector
```

Next milestone: after BloodHound ingestion, the graph should have
User, Computer, Group, Domain nodes from ETHBANK.LOCAL merged with
the existing ETI-Core data — all queryable together.

---

## Key Cypher Queries

Check everything is loaded:
```cypher
MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count ORDER BY count DESC
```

See threat actor relationships:
```cypher
MATCH (a:ThreatActor)-[r]->(n) RETURN a.name, type(r), n.name
```

Find attack paths (after BloodHound ingestion):
```cypher
MATCH p = shortestPath((u:User)-[*1..5]->(g:Group {name: 'DOMAIN ADMINS@ETHBANK.LOCAL'}))
RETURN p LIMIT 10
```

Check nodes by source:
```cypher
MATCH (n) WHERE n.source = 'bloodhound' RETURN labels(n), count(n)
MATCH (n) WHERE n.source = 'eti-core' RETURN labels(n), count(n)
```
