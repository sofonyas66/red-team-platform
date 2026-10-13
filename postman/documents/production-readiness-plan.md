# ETHIO-RTAP — Production Readiness Plan

> **Status:** Demo → Production  
> **Platform:** Red Team Planning & Analysis Platform (INSA Ethiopia)

---

## Executive Summary

The platform has a solid architectural foundation: a FastAPI backend, Neo4j graph database, Qdrant vector store, a trained R-GAT (PathGAT) model, RAG-based threat intelligence retrieval, and an LLM campaign planner. The core pipeline works end-to-end. What's missing is the hardening, reliability, and operational scaffolding needed to run this in a real red team environment.

This plan is organized into **5 tracks** that can be worked in parallel by different team members.

---

## Track 1 — Security Hardening

These are blockers. None of the below should go to production as-is.

### 1.1 Secrets Management
- **Problem:** `graph/schema.py` and `eti_core/loader.py` have hardcoded `bolt://localhost:7687` and `("neo4j", "changeme")` credentials. `api/auth.py` has a hardcoded `JWT_SECRET_KEY = "dev-secret-change-in-production"`.
- **Fix:** All three files must read from environment variables (already done in `graph/connection.py` — replicate that pattern). Rotate the JWT secret and load it from `.env` / a secrets manager.

### 1.2 Authentication — Real Password Verification
- **Problem:** `api/auth.py` has `USERS_DB` with dummy `$2b$12$dummy` password hashes. The login endpoint accepts any password for known usernames.
- **Fix:** Implement real `bcrypt` password verification using `passlib`. In production, back this with a database (PostgreSQL or LDAP). Add a user management endpoint (admin-only) to create/update users.

### 1.3 CORS Lockdown
- **Problem:** `allow_origins=["*"]` in `api/main.py`.
- **Fix:** Restrict to known frontend origins via an `ALLOWED_ORIGINS` environment variable.

### 1.4 Input Validation
- **Problem:** `source` and `target` query parameters in `GET /paths` are passed directly into Cypher queries via `find_and_score_paths()`. While parameterized, the values are not validated for length or character set.
- **Fix:** Add Pydantic validators or FastAPI `Query(min_length=1, max_length=256, pattern=...)` constraints on all user-supplied graph identifiers.

### 1.5 Rate Limiting — Persistent Backend
- **Problem:** `slowapi` with `get_remote_address` is in-memory and resets on restart. Behind a load balancer, IP-based limiting is trivially bypassed.
- **Fix:** Switch to Redis-backed rate limiting (`slowapi` supports this). Add Redis to `docker-compose.yml`.

---

## Track 2 — Reliability & Data Layer

### 2.1 Fix Hardcoded Credentials in `schema.py` and `loader.py`
Both files create their own `GraphDatabase.driver` with hardcoded credentials instead of importing the shared `driver` from `graph/connection.py`.
- **Fix:** Refactor both to use `from graph.connection import driver`.

### 2.2 Persistent User Store
- **Problem:** `USERS_DB` in `api/auth.py` is an in-memory dict. Users are lost on restart.
- **Fix:** Add a `users` table to a PostgreSQL instance (add to `docker-compose.yml`) or use a simple SQLite DB for single-node deployments.

### 2.3 Ingestion Log — Persistent Storage
- **Problem:** `INGESTION_TRACKER_FILE` is a JSON file on disk (`data/ingestion_log.json`). This doesn't scale and is lost if the container is ephemeral.
- **Fix:** Move ingestion tracking to Neo4j (a dedicated `IngestionRecord` node) or PostgreSQL.

### 2.4 GNN Cache Invalidation
- **Problem:** `gnn/cache/` contains pre-built `.pt` files. If new BloodHound data is ingested, the GAT model and tensors are stale but the cache is never invalidated.
- **Fix:** After a successful `/ingest/bloodhound` call, delete the GAT cache files and reset `_GAT_STATE = None` in `gnn/init_gat.py` so the model re-trains on the next path query. Add a background task (FastAPI `BackgroundTasks`) to re-train asynchronously.

### 2.5 Async Neo4j Driver
- **Problem:** All Neo4j calls use the synchronous `driver.session()` inside async FastAPI route handlers, blocking the event loop.
- **Fix:** Switch to `AsyncGraphDatabase.driver` from the `neo4j` Python package and use `async with driver.session() as session` / `await session.run(...)`.

### 2.6 `pyproject.toml` — Pin Dependencies
- **Problem:** `requirements.txt` has no version pins. `torch`, `torch-geometric`, and `neo4j` have breaking changes between versions.
- **Fix:** Pin all dependencies with minimum versions. Add a `pyproject.toml` `[project.optional-dependencies]` section for dev tools.

---

## Track 3 — API Completeness

### 3.1 Missing Endpoints
The following endpoints are needed for a complete operational platform:

| Endpoint | Method | Description |
|---|---|---|
| `POST /auth/logout` | POST | Invalidate token (requires token blocklist in Redis) |
| `GET /actors/{actor_id}` | GET | Get a single threat actor by ID |
| `GET /graph/nodes` | GET | List/search nodes (paginated) |
| `DELETE /graph/reset` | DELETE | Clear the graph (admin only) |
| `POST /gnn/retrain` | POST | Manually trigger GNN re-training |
| `GET /ingestion/history/{hash}` | GET | Get details for a specific ingestion |

### 3.2 Pagination
- `GET /actors` returns all actors with no limit. Add `skip` / `limit` query parameters.

### 3.3 Structured Error Responses
- **Problem:** Errors return raw `str(e)` exception messages, leaking internal details.
- **Fix:** Define a standard `ErrorResponse` Pydantic model. Catch specific exceptions and return sanitized messages. Log full tracebacks server-side only.

### 3.4 API Versioning
- **Fix:** Prefix all routes with `/api/v1/` using a FastAPI `APIRouter`. This allows future breaking changes without disrupting existing clients.

---

## Track 4 — Testing & Observability

### 4.1 Test Suite
There is currently no `tests/` directory. The `Makefile` falls back to running `bootstrap.py` when pytest finds nothing.

**Required tests:**
- `tests/test_auth.py` — login, token validation, role enforcement
- `tests/test_ingest.py` — valid zip upload, duplicate detection, invalid file rejection
- `tests/test_paths.py` — path finding with mock Neo4j data
- `tests/test_health.py` — health endpoint with Neo4j up/down

Use `pytest` + `httpx.AsyncClient` for async FastAPI testing. Mock Neo4j with `unittest.mock` or `pytest-mock`.

### 4.2 Postman Collection Tests
Add pre-request and test scripts to the existing Postman collection:
- **Login:** Auto-save `access_token` to the `authToken` collection variable.
- **All authenticated endpoints:** Assert `200` status and validate response schema.
- **Error cases:** Assert `401` on missing token, `403` on wrong role, `400` on bad input.

### 4.3 Structured Logging
- **Problem:** The codebase mixes `print()` and `logging.basicConfig()` inconsistently.
- **Fix:** Standardize on Python `logging` with a JSON formatter (e.g., `python-json-logger`). Add request ID middleware to correlate logs across a request lifecycle.

### 4.4 Health Check Enhancement
Extend `GET /health` to also check Qdrant connectivity:
```python
qdrant.get_collections()  # add to health check
```
Return a structured response with per-service status so load balancers and monitors can act on it.

### 4.5 Postman Monitor
Set up a Postman Monitor on the collection to run the health check and graph stats endpoints on a schedule (e.g., every 15 minutes) to detect outages.

---

## Track 5 — Deployment & Infrastructure

### 5.1 Environment Configuration
- **Problem:** No `.env.example` file exists (referenced in `Makefile` but missing).
- **Fix:** Create `.env.example` with all required variables documented:
  ```
  NEO4J_URI=bolt://localhost:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=changeme
  JWT_SECRET_KEY=change-this-to-a-random-256-bit-secret
  QDRANT_URL=http://localhost:6333
  LLM_PROVIDER=api
  ANTHROPIC_API_KEY=
  OPENAI_API_KEY=
  GEMINI_API_KEY=
  OPENROUTER_API_KEY=
  ALLOWED_ORIGINS=http://localhost:3000
  ```

### 5.2 Docker — Production Image
- **Problem:** No `Dockerfile` for the API service itself (only infrastructure in `docker-compose.yml`).
- **Fix:** Add an `api` service to `docker-compose.yml` that builds from the existing `Dockerfile`. Add health checks and `depends_on` with `condition: service_healthy` for Neo4j and Qdrant.

### 5.3 GNN Re-training Pipeline
The GNN training (`gnn/embeddings.py` + `gnn/init_gat.py`) is a long-running CPU/GPU task. It should not block API requests.
- **Fix:** Add a Celery worker (or use FastAPI `BackgroundTasks` for simpler cases) to handle re-training asynchronously. Expose progress via `GET /gnn/status`.

### 5.4 Data Backup
- Add a `make backup` target that dumps Neo4j data and Qdrant snapshots to a timestamped archive.

---

## Priority Order (Suggested Sprint Plan)

### Sprint 1 — Security & Stability (Week 1)
1. Fix hardcoded credentials in `schema.py` and `loader.py`
2. Implement real bcrypt password verification
3. Restrict CORS origins
4. Add `.env.example`
5. Rotate JWT secret key

### Sprint 2 — Reliability (Week 2)
1. Switch to async Neo4j driver
2. Move ingestion log to Neo4j
3. Implement GNN cache invalidation on ingest
4. Add Redis to docker-compose for rate limiting
5. Pin all dependencies

### Sprint 3 — API & Testing (Week 3)
1. Add missing endpoints (logout, retrain, reset)
2. Add API versioning (`/api/v1/`)
3. Write core test suite (auth, ingest, health)
4. Add Postman test scripts (auto-save token, schema assertions)
5. Structured error responses

### Sprint 4 — Observability & Deployment (Week 4)
1. Structured JSON logging
2. Enhanced health check (Qdrant + Neo4j)
3. Production Docker Compose with API service
4. Postman Monitor setup
5. Data backup strategy

---

## Open Questions

- **Frontend:** Is there a web UI planned, or is the CLI + API the primary interface?
- **Multi-tenancy:** Should different red team operators be isolated from each other's data?
- **Offline mode:** The Ollama service is commented out in `docker-compose.yml`. Is air-gapped / offline operation a requirement?
- **Scale:** Expected concurrent users? This affects whether a single-node deployment is sufficient or a clustered Neo4j + load-balanced API is needed.

---

*Generated by Postman Agent — based on codebase analysis of `/home/klythron/Documents/projucts/red-team-platform`*
