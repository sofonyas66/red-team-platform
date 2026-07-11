# ETHIO-RTAP — Red Team Planning & Analysis Platform

> **AI-Powered Attack Path Discovery, GNN Risk Scoring & Campaign Generation**
> *Developed for the INSA Ethio Cyber Talent Program — Red Team Track*

---

## Overview

ETHIO-RTAP is an enterprise-grade red team planning platform that models Active Directory environments, discovers lateral movement attack paths, scores traversal risk using Graph Neural Networks, correlates paths with real-world threat actors, and generates actionable campaign playbooks using LLMs.

## One-Command Setup

We have simplified the setup process into a single command. The `Makefile` and `run.sh` script automatically detect your environment (Docker/Podman/Compose), handle dependency installation, and configure the infrastructure.

### 1. Initial Setup
Clone the repository and run the setup command:

```bash
git clone <repository-url>
cd red-team-platform

# This sets up venv, installs dependencies, and creates a .env file
make install
```

### 2. Configure Environment
Edit the generated `.env` file to add your required API keys (Gemini, OpenAI, Anthropic, or OpenRouter):

```bash
# Open your .env file
nano .env
```

### 3. Start Platform
Use the `bootstrap` command to initialize databases, load threat intelligence, and configure embeddings in one go:

```bash
make bootstrap
```

### 4. Run API
Start the FastAPI server:

```bash
make api
```

---

## Command Reference

| Command | Description |
| :--- | :--- |
| `make bootstrap` | Start databases, load threat intel, initialize RAG/GNN. |
| `make api` | Start the FastAPI backend server. |
| `make up` | Start only the Neo4j/Qdrant containers. |
| `make test` | Run health checks and test suite. |
| `make clean` | Remove containers, volumes, and temporary files. |

---

## Architecture & Pipeline

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
```

## Security Notice
This platform is designed exclusively for **authorized cybersecurity research** and red team emulation exercises. Ensure you have the appropriate permissions before modeling any production environment.
