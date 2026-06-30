# Red Team Planning and Analysis Platform
> **Automated Attack Path Discovery, GNN Risk Scoring, and AI-Driven Campaign Generation**
>
> *Developed for the INSA Ethio Cyber Talent Program — Red Team Track*

---

## 📋 Overview

The **Red Team Planning and Analysis Platform** is an enterprise-grade AI-powered cyber security solution designed to model Active Directory (AD) environments, discover lateral movement paths, score traversal risk using Graph Neural Networks (GNNs), correlate vulnerability paths with real-world threat actors, and generate actionable campaign plans.

By uniting **Neo4j** (knowledge graph database), **Qdrant** (vector store database), **PyTorch Geometric** (structural graph embeddings), and **Advanced LLMs** (Anthropic, OpenAI, Gemini, OpenRouter, or local Ollama), this platform enables automated security assessments and red team emulation planning.

---

## 🏗️ Architecture & Data Flow

The platform executes an end-to-end pipeline that transforms raw configuration exports and threat intelligence feeds into ready-to-execute red team campaign manuals.

```
+------------------------+      +--------------------------+
|  BloodHound AD JSON    |      |  STIX 2.1 Intel Bundles  |
+-----------+------------+      +------------+-------------+
            |                                |
            | (etl/bloodhound.py)            | (eti_core/loader.py)
            +----------------+---------------+
                             |
                             ▼
                   +-------------------+
                   |    Neo4j Graph    | <---+ (graph/schema.py)
                   +---------+---------+
                             |
         +-------------------+-------------------+
         |                                       |
         ▼ (gnn/embeddings.py)                   ▼ (llm/rag.py)
  +--------------+                        +--------------+
  |  Node2Vec    |                        |  Qdrant      |
  |  Embeddings  |                        |  Vector DB   |
  +------+-------+                        +------+-------+
         |                                       |
         ▼ (llm/planner.py)                      |
  +--------------+                               |
  |  Attack Path |                               |
  |  GNN Scoring |                               |
  +------+-------+                               |
         |                                       |
         +-------------------+-------------------+
                             |
                             ▼
                    +------------------+
                    |  LLM Planner     | (llm/provider.py)
                    +--------+---------+
                             |
                             ▼
                    +------------------+
                    |  Campaign Plan   | (FastAPI / CLI)
                    +------------------+
```

### The 5-Step Pipeline:
1. **Graph Ingestion**: Merges Active Directory structure (users, groups, computers, domains) with External Threat Intelligence Core (ETI-Core) threat actors, techniques, and target sectors into a single Neo4j database.
2. **GNN Representation Learning**: Runs a PyTorch Geometric-based **Node2Vec** representation model to train 128-dimensional structural embeddings for every node in the graph, which are saved directly back to Neo4j.
3. **Attack Path Scoring**: Finds candidate paths from a compromised source to critical assets and scores each transition based on the cosine similarity of their learned structural node embeddings.
4. **Threat Intelligence RAG**: Scopes technique signatures to the most relevant Threat Actors, embeds threat profiles via SentenceTransformers (`all-MiniLM-L6-v2`), and queries Qdrant vector database for specialized emulation details.
5. **AI Campaign Planner**: Integrates scored paths, threat actor profiles, and retrieved context to output a comprehensive campaign playbook via an LLM.

---

## 📁 Project Directory Structure

```
red-team-platform/
│
├── graph/                  # Graph Database Layer
│   ├── __init__.py
│   ├── connection.py       # Neo4j Driver Connection Setup
│   └── schema.py           # Database Constraints and Indexes
│
├── eti_core/               # Threat Intelligence Module
│   ├── __init__.py
│   ├── loader.py           # STIX 2.1 Parser and Graph Ingester
│   └── actors/             # STIX 2.1 Threat Actor JSON Bundles
│       ├── financial.json
│       └── state_affiliated.json
│
├── etl/                    # Extraction and Ingestion Pipelines
│   ├── __init__.py
│   └── bloodhound.py       # BloodHound JSON AD Ingestion
│
├── gnn/                    # Graph Representation Learning
│   ├── __init__.py
│   └── embeddings.py       # PyTorch Geometric Node2Vec Embeddings Generator
│
├── llm/                    # Language Model Reasoning Layer
│   ├── __init__.py
│   ├── provider.py         # Modular LLM Abstraction Client (OpenAI, Gemini, Anthropic, Ollama)
│   ├── rag.py              # Qdrant Vector Store Setup and Context Retriever
│   └── planner.py          # AI Campaign Planner Orchestration
│
├── api/                    # REST API Layer
│   ├── __init__.py
│   └── main.py             # FastAPI REST Server
│
├── data/
│   └── sample/
│       └── bloodhound_sample.json # Sample AD environment data for testing
│
├── .env                    # System Configuration Settings
├── Dockerfile              # Docker Container Build File
├── docker-compose.yml      # Multi-Container Deployment Configuration
├── requirements.txt        # Python Packages and Dependencies
└── README.md               # System Documentation (This file)
```

---

## ⚙️ Configuration & Setup

### Prerequisites
- Python 3.10 or 3.11
- Docker and Docker Compose (recommended)

### 1. Database Infrastructure Setup
You can spin up both Neo4j and Qdrant containers in one command:

```bash
docker compose up -d
```

This starts:
- **Neo4j** on `bolt://localhost:7687` and browser portal on `http://localhost:7474` (Credentials: `neo4j` / `changeme`)
- **Qdrant** vector database on `http://localhost:6333`
- **FastAPI API Server** on `http://localhost:8000`

---

### 2. Environment Settings
Create or update the `.env` file in the project root directory:

```env
# === LLM Configuration ===
# Provider Options: "api" (cloud APIs) or "ollama" (local engine)
LLM_PROVIDER=api

# Cloud API Keys (Set at least one if LLM_PROVIDER=api)
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
GEMINI_API_KEY=your_gemini_key_here

# === Database Infrastructure ===
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

---

### 3. Local Python Environment Setup
If running the scripts directly on your host machine, build the virtual environment:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🚀 Execution Guide

### Option A: End-to-End Demonstration Script
To verify the entire environment and view a complete run (Graph stats -> Attack paths -> GNN scoring -> Threat Intel correlation -> Campaign generation), run the demo script:

```bash
python demo.py
```
*Note: Use `--fast` flag to skip section-by-section sleep timers.*

---

### Option B: Step-by-Step Command Line Pipeline

#### Step 1: Initialize Database Schema
Create labels, uniqueness constraints, and search indexes in Neo4j:
```bash
python graph/schema.py
```

#### Step 2: Load Threat Intelligence Data
Ingest STIX 2.1 threat profiles (actors, techniques, tactics, target sectors) from `eti_core/actors/`:
```bash
python eti_core/loader.py
```

#### Step 3: Ingest Active Directory Data
Load your BloodHound JSON network export into the graph database:
```bash
python etl/bloodhound.py data/sample/bloodhound_sample.json
```

#### Step 4: Run GNN Node2Vec Training
Train structural node embeddings for all AD systems and threat techniques:
```bash
python gnn/embeddings.py
```

#### Step 5: Index Threat Intelligence in Qdrant Vector Store
Generate vector embeddings for all threat intelligence descriptions and store them in Qdrant:
```bash
python llm/rag.py
```

---

## 🔌 API Documentation

Run the API locally (or through Docker Compose):
```bash
python -m api.main
```
Interactive OpenAPI documentation will be available at `http://localhost:8000/docs`.

### Key REST Endpoints:

#### 1. System Health Check
* **Endpoint**: `GET /health`
* **Description**: Verifies API operation and database connectivity.
* **Response**:
  ```json
  {"status": "ok", "neo4j": true}
  ```

#### 2. Graph Database Statistics
* **Endpoint**: `GET /graph/stats`
* **Description**: Outputs current node and edge counts grouped by label.

#### 3. Upload BloodHound Export
* **Endpoint**: `POST /ingest/bloodhound`
* **Payload**: Form-data file containing BloodHound JSON.
* **Description**: Parses and inserts AD network data into the Neo4j schema.
* **Response**:
  ```json
  {
    "status": "success",
    "nodes_ingested": 9,
    "relationships_ingested": 10
  }
  ```

#### 4. Find Scored Attack Paths
* **Endpoint**: `GET /paths`
* **Query Parameters**: `source` (User name), `target` (Computer name)
* **Description**: Returns all paths between source and target, ranked by their GNN-derived traversal risk.
* **Example Request**: `/paths?source=hr_user01@ETHBANK.LOCAL&target=DC01.ETHBANK.LOCAL`

#### 5. Generate Campaign Plan
* **Endpoint**: `POST /plan/generate`
* **Body**:
  ```json
  {
    "source": "hr_user01@ETHBANK.LOCAL",
    "target": "DC01.ETHBANK.LOCAL"
  }
  ```
* **Description**: Extracts the top attack paths, fetches TI context from Qdrant, and builds a comprehensive emulation plan using the LLM.

---

## 🔍 Database Inspection & Cypher Cheat Sheet

Interact with the graph database directly via the Neo4j Browser at `http://localhost:7474`.

### Count All Nodes by Label:
```cypher
MATCH (n) 
RETURN labels(n)[0] AS NodeLabel, count(n) AS TotalCount 
ORDER BY TotalCount DESC
```

### Check Nodes Based on Ingestion Source:
```cypher
MATCH (n) 
RETURN n.source AS SourceType, count(n) AS TotalCount
```

### View Threat Actors and their USES/TARGETS Relationships:
```cypher
MATCH (a:ThreatActor)-[r]->(n) 
RETURN a.name AS ThreatActor, type(r) AS Relationship, n.name AS Target
```

### Find Shortest Paths from a User to Domain Admins Group:
```cypher
MATCH p = shortestPath((u:User)-[*1..5]->(g:Group {name: 'DOMAIN ADMINS@ETHBANK.LOCAL'}))
RETURN p 
LIMIT 10
```

### List Nodes with GNN Embeddings:
```cypher
MATCH (n) 
WHERE n.embedding IS NOT NULL 
RETURN labels(n)[0] AS Type, n.name AS Name, size(n.embedding) AS VectorDimensions 
LIMIT 10
```

---

## 📝 License & Project Details

* **Project Title**: Red Team Planning and Analysis Platform
* **Affiliation**: INSA Ethio Cyber Talent Program — Red Team Track
* **Security Notice**: This platform is designed exclusively for authorized cybersecurity research, red-teaming emulation exercises, and security planning. Make sure to obtain proper authorization before scanning or modeling production networks.
