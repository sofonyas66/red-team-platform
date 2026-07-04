"""
api/main.py — FastAPI application for Red Team Planning Platform (Production-ready)
"""
import os
import json
import hashlib
import tempfile
import zipfile
import shutil
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager

from graph.connection import driver
from etl.bloodhound import ingest_bloodhound as ingest_data
from llm.planner import find_and_score_paths, generate_campaign_plan
from api.auth import (
    get_current_user, require_roles, optional_auth, create_access_token,
    User, TokenData, PUBLIC_PATHS
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Ingestion tracking (in production: Redis/DB)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
INGESTION_TRACKER_FILE = os.path.join(DATA_DIR, "ingestion_log.json")

def load_ingestion_log() -> Dict[str, Dict]:
    if os.path.exists(INGESTION_TRACKER_FILE):
        with open(INGESTION_TRACKER_FILE) as f:
            return json.load(f)
    return {}

def save_ingestion_log(log: Dict[str, Dict]):
    os.makedirs(os.path.dirname(INGESTION_TRACKER_FILE), exist_ok=True)
    with open(INGESTION_TRACKER_FILE, "w") as f:
        json.dump(log, f, indent=2)

def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def is_already_ingested(content_hash: str) -> bool:
    log = load_ingestion_log()
    return content_hash in log

def record_ingestion(content_hash: str, filename: str, result: Dict):
    log = load_ingestion_log()
    log[content_hash] = {
        "filename": filename,
        "ingested_at": datetime.utcnow().isoformat(),
        "result": result
    }
    save_ingestion_log(log)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(DATA_DIR, exist_ok=True)
    yield
    # Shutdown cleanup

app = FastAPI(
    title="Red Team Planning Platform API",
    description="INSA Ethiopia — Automated Attack Path Analysis & Campaign Planning",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# =============================================================================
# Pydantic Models
# =============================================================================

class PlanRequest(BaseModel):
    source: str
    target: str

class TokenRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class IngestResponse(BaseModel):
    status: str
    nodes_ingested: Dict[str, int] = {}
    relationships_ingested: Dict[str, int] = {}
    skipped_ace_types: List[str] = []
    computers_with_uncollected_sessions: int = 0
    computers_with_uncollected_localgroups: int = 0
    skipped: bool = False
    message: str = ""

# =============================================================================
# Middleware
# =============================================================================

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth for public paths
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    # Auth is handled by Depends() in each endpoint
    return await call_next(request)

# =============================================================================
# Auth Endpoints
# =============================================================================

@app.post("/auth/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, credentials: TokenRequest):
    """Obtain JWT token. In production, verify password hash."""
    # Demo: accept any password for known users
    from api.auth import USERS_DB
    if credentials.username not in USERS_DB:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = USERS_DB[credentials.username]
    access_token = create_access_token(
        data={"sub": credentials.username, "roles": user["roles"]}
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=60 * 24 * 60  # 24 hours in seconds
    )

# =============================================================================
# Core Endpoints
# =============================================================================

@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
    try:
        with driver.session() as session:
            session.run("RETURN 1")
        return {"status": "ok", "neo4j": True, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "neo4j": False, "detail": str(e)}
        )

@app.get("/graph/stats")
@limiter.limit("30/minute")
async def graph_stats(request: Request, user: User = Depends(get_current_user)):
    try:
        with driver.session() as session:
            node_result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] AS type, count(n) AS count
                ORDER BY count DESC
            """)
            nodes = {r["type"]: r["count"] for r in node_result}
            
            rel_result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(r) AS count
                ORDER BY count DESC
            """)
            relationships = {r["type"]: r["count"] for r in rel_result}
            
            return {"nodes": nodes, "relationships": relationships}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
def _safe_extract_zip(zip_path: str, extract_to: str):
    """Extract a zip file, guarding against zip-slip path traversal."""
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            member_path = os.path.normpath(os.path.join(extract_to, member))
            if not member_path.startswith(os.path.normpath(extract_to) + os.sep):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsafe path in zip archive: {member}"
                )
        zf.extractall(extract_to)


@app.post("/ingest/bloodhound", response_model=IngestResponse)
@limiter.limit("10/hour")
async def upload_bloodhound(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_roles("admin", "analyst"))
):
    if not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail="File must be a .zip archive of SharpHound JSON exports"
        )

    content = await file.read()
    content_hash = file_hash(content)

    if is_already_ingested(content_hash):
        return IngestResponse(
            status="skipped",
            skipped=True,
            message=f"File already ingested (hash: {content_hash[:16]}...)"
        )

    extract_dir = tempfile.mkdtemp(prefix="bloodhound_ingest_")
    zip_path = os.path.join(extract_dir, "upload.zip")

    try:
        with open(zip_path, "wb") as f:
            f.write(content)

        _safe_extract_zip(zip_path, extract_dir)
        os.unlink(zip_path)

        json_files = [f for f in os.listdir(extract_dir) if f.endswith(".json")]
        if not json_files:
            raise HTTPException(
                status_code=400,
                detail="No .json files found in the uploaded zip"
            )

        result = ingest_data(extract_dir)
        record_ingestion(content_hash, file.filename, result)

        return IngestResponse(
            status="success",
            nodes_ingested=result["nodes_ingested"],
            relationships_ingested=result["relationships_ingested"],
            skipped_ace_types=result["skipped_ace_types"],
            computers_with_uncollected_sessions=result["computers_with_uncollected_sessions"],
            computers_with_uncollected_localgroups=result["computers_with_uncollected_localgroups"],
            message="Ingestion complete",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)

@app.get("/paths")
@limiter.limit("30/minute")
async def get_paths(
    request: Request,
    source: str,
    target: str,
    user: User = Depends(get_current_user)
):
    try:
        paths = find_and_score_paths(source, target)
        return paths
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plan/generate")
@limiter.limit("10/minute")
async def plan_generate(
    request: Request,
    plan_request: PlanRequest,
    user: User = Depends(require_roles("admin", "analyst"))
):
    try:
        plan_text = generate_campaign_plan(plan_request.source, plan_request.target)
        return {"plan": plan_text, "generated_by": user.username, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/actors")
@limiter.limit("30/minute")
async def get_actors(request: Request, user: User = Depends(get_current_user)):
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (a:ThreatActor)
                OPTIONAL MATCH (a)-[:USES]->(t:Technique)
                RETURN a.name AS actor_name,
                       a.motivation AS motivation,
                       a.sophistication AS sophistication,
                       collect(DISTINCT t.name) AS techniques
            """)
            
            actors = []
            for record in result:
                actors.append({
                    "actor_name": record["actor_name"],
                    "motivation": record["motivation"],
                    "sophistication": record["sophistication"],
                    "techniques": record["techniques"]
                })
            return actors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ingestion/history")
@limiter.limit("10/minute")
async def ingestion_history(request: Request, user: User = Depends(require_roles("admin"))):
    """View ingestion history (admin only)."""
    log = load_ingestion_log()
    return {"history": log}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
