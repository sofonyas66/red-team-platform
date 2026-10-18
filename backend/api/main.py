"""
api/main.py — FastAPI application for Red Team Planning Platform (Production-ready)
"""
import os
import uuid
from fastapi import Form, Body
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select
import hashlib
import tempfile
import zipfile
import shutil
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager

from graph.connection import get_driver
from etl.bloodhound import ingest_bloodhound as ingest_data
from llm.planner import find_and_score_paths, generate_campaign_plan
from config import ALLOWED_ORIGINS, _sync_url
from api.auth import (
    get_current_user, require_roles, optional_auth, create_access_token,
    authenticate_user, AuthenticatedUser, TokenData, PUBLIC_PATHS
)
from db.ingestion_ops import (
    is_already_ingested as pg_is_already_ingested,
    record_ingestion as pg_record_ingestion,
    get_ingestion_record_by_hash,
    _engine as _ingestion_engine,
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown cleanup

app = FastAPI(
    title="Red Team Planning Platform API",
    description="INSA Ethiopia — Automated Attack Path Analysis & Campaign Planning",
    version="1.0.0",
    lifespan=lifespan
)

# CORS — origins driven by ALLOWED_ORIGINS env var (never wildcard in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
    """Obtain JWT token. Verifies bcrypt password against Postgres."""
    user = authenticate_user(credentials.username, credentials.password)
    access_token = create_access_token(data={
        "sub": str(user.id),
        "org_id": str(user.org_id),
        "role": user.role.value,
    })
    return TokenResponse(
        access_token=access_token,
        expires_in=60 * 24 * 60,  # 24 hours in seconds
    )


@app.post("/auth/logout")
@limiter.limit("30/minute")
async def logout(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    """Invalidate the current token.
    TODO: add token to Redis-backed blocklist (Track 1.5).
    For now this is a stub — the client should discard the token locally.
    """
    return {"detail": "Logged out. Token blocklist not yet implemented (Track 1.5 stub)."}


@app.get("/me")
@limiter.limit("10/minute")
async def get_me(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    from db.models import User, Organization
    with Session(_ingestion_engine) as session:
        stmt = select(User).where(User.id == uuid.UUID(user.id))
        db_user = session.scalar(stmt)
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        stmt = select(Organization).where(Organization.id == db_user.org_id)
        org = session.scalar(stmt)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        return {
            "id": str(db_user.id),
            "email": db_user.email,
            "role": db_user.role.value,
            "org_name": org.name
        }

# =============================================================================
# Core Endpoints
# =============================================================================

# END NEW: Engagements endpoints

@app.get("/engagements")
@limiter.limit("10/minute")
async def get_engagements(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    from db.models import Engagement
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    with Session(_ingestion_engine) as session:
        stmt = select(Engagement).where(Engagement.org_id == uuid.UUID(user.org_id))
        engagements = session.scalars(stmt).all()
    return [
        {"id": str(e.id), "name": e.name}
        for e in engagements
    ]

class CreateEngagementRequest(BaseModel):
    name: str

@app.post("/engagements")
@limiter.limit("5/minute")
async def create_engagement(request: Request, payload: CreateEngagementRequest, user: AuthenticatedUser = Depends(require_roles("org_admin", "operator"))):
    from db.models import Engagement
    from sqlalchemy.orm import Session
    with Session(_ingestion_engine) as session:
        new = Engagement(org_id=uuid.UUID(user.org_id), name=payload.name, created_by=uuid.UUID(user.id))
        session.add(new)
        session.commit()
        session.refresh(new)
    return {"id": str(new.id), "name": new.name}

@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
    try:
        async with get_driver().session() as session:
            await session.run("RETURN 1")
        return {"status": "ok", "neo4j": True, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "neo4j": False, "detail": str(e)}
        )

@app.get("/graph/stats")
@limiter.limit("30/minute")
async def graph_stats(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        async with get_driver().session() as session:
            node_result = await session.run("""
                MATCH (n)
                WHERE n.org_id = $org_id
                RETURN labels(n)[0] AS type, count(n) AS count
                ORDER BY count DESC
            """, org_id=user.org_id)
            nodes = {r["type"]: r["count"] async for r in node_result}

            rel_result = await session.run("""
                MATCH (s)-[r]->(t)
                WHERE s.org_id = $org_id AND t.org_id = $org_id
                RETURN type(r) AS type, count(r) AS count
                ORDER BY count DESC
            """, org_id=user.org_id)
            relationships = {r["type"]: r["count"] async for r in rel_result}

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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    engagement_id: uuid.UUID = Form(...),
    user: AuthenticatedUser = Depends(require_roles("org_admin", "operator"))):
    # Validate engagement belongs to org
    from db.models import Engagement
    with Session(_ingestion_engine) as db_session:
        stmt = select(Engagement).where(Engagement.id == engagement_id,
                                        Engagement.org_id == uuid.UUID(user.org_id))
        engagement = db_session.scalar(stmt)
        if not engagement:
            raise HTTPException(status_code=404, detail="Engagement not found for your org")

    engagement_id_str = str(engagement_id)

    if not file.filename.endswith('.zip'):

        raise HTTPException(
            status_code=400,
            detail="File must be a .zip archive of SharpHound JSON exports"
        )

    content = await file.read()
    content_hash = file_hash(content)

    if pg_is_already_ingested(str(user.org_id), content_hash):
        raise HTTPException(status_code=409, detail=f"File already ingested (hash: {content_hash[:16]}...)")

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

        result = await ingest_data(extract_dir, org_id=str(user.org_id), engagement_id=engagement_id_str)
        total_nodes = sum(result["nodes_ingested"].values())
        total_edges = sum(result["relationships_ingested"].values())
        try:
            pg_record_ingestion(
                org_id=str(user.org_id),
                engagement_id=engagement_id_str,
                file_hash=content_hash,
                filename=file.filename,
                node_count=total_nodes,
                edge_count=total_edges,
                ingested_by=str(user.id),
            )
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Ingestion record already exists (unique constraint)")

        from gnn.init_gat import invalidate_gat_state, retrain_gat_background
        invalidate_gat_state(org_id=str(user.org_id), engagement_id=engagement_id_str)
        background_tasks.add_task(retrain_gat_background, str(user.org_id), engagement_id_str)

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
    engagement_id: str = "",
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        paths = await find_and_score_paths(source, target, org_id=str(user.org_id), engagement_id=engagement_id)
        return paths
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"ML stack not available on this instance: {e}. "
                   "Install torch and torch_geometric to enable path scoring.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plan/generate")
@limiter.limit("10/minute")
async def plan_generate(
    request: Request,
    plan_request: PlanRequest,
    engagement_id: str = "",
    user: AuthenticatedUser = Depends(require_roles("org_admin", "operator"))
):
    try:
        plan_text = await generate_campaign_plan(plan_request.source, plan_request.target, org_id=str(user.org_id), engagement_id=engagement_id)
        return {"plan": plan_text, "generated_by": user.id, "timestamp": datetime.utcnow().isoformat()}
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"ML stack not available on this instance: {e}. "
                   "Install torch, torch_geometric, and sentence-transformers to enable plan generation.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/gnn/status")
@limiter.limit("60/minute")
async def gnn_status(
    request: Request,
    engagement_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    from gnn.init_gat import get_retrain_status
    status = get_retrain_status(str(user.org_id), engagement_id)
    return {"org_id": str(user.org_id), "engagement_id": engagement_id, **status}

@app.get("/actors")
@limiter.limit("30/minute")
async def get_actors(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        async with get_driver().session() as session:
            result = await session.run("""
                MATCH (a:ThreatActor)
                OPTIONAL MATCH (a)-[:USES]->(t:Technique)
                RETURN a.name AS actor_name,
                       a.motivation AS motivation,
                       a.sophistication AS sophistication,
                       collect(DISTINCT t.name) AS techniques
            """)
            actors = [
                {
                    "actor_name": record["actor_name"],
                    "motivation": record["motivation"],
                    "sophistication": record["sophistication"],
                    "techniques": record["techniques"],
                }
                async for record in result
            ]
            return actors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ingestion/history")
@limiter.limit("10/minute")
async def ingestion_history(
    request: Request,
    user: AuthenticatedUser = Depends(require_roles("org_admin")),
):
    """View recent ingestion history for this org (admin only)."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session as DBSession
    from db.models import IngestionRecord
    from db.ingestion_ops import _engine
    import uuid as _uuid
    with DBSession(_engine) as session:
        stmt = select(IngestionRecord).where(
            IngestionRecord.org_id == _uuid.UUID(str(user.org_id))
        ).order_by(IngestionRecord.ingested_at.desc()).limit(50)
        records = session.scalars(stmt).all()
    return {"history": [
        {
            "id": str(r.id),
            "file_hash": r.file_hash,
            "filename": r.filename,
            "status": r.status.value,
            "node_count": r.node_count,
            "edge_count": r.edge_count,
            "ingested_at": r.ingested_at.isoformat(),
        }
        for r in records
    ]}


@app.get("/ingestion/history/{file_hash}")
@limiter.limit("30/minute")
async def ingestion_record_by_hash(
    request: Request,
    file_hash: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Return the ingestion record for a specific file hash, scoped to this org."""
    record = get_ingestion_record_by_hash(str(user.org_id), file_hash)
    if not record:
        raise HTTPException(status_code=404, detail=f"No ingestion record found for hash {file_hash[:16]}... in your org")
    return {
        "id": str(record.id),
        "org_id": str(record.org_id),
        "engagement_id": str(record.engagement_id),
        "file_hash": record.file_hash,
        "filename": record.filename,
        "status": record.status.value,
        "node_count": record.node_count,
        "edge_count": record.edge_count,
        "ingested_at": record.ingested_at.isoformat(),
        "ingested_by": str(record.ingested_by),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
