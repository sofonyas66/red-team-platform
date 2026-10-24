"""
api/main.py — FastAPI application for Red Team Planning Platform (Production-ready)
"""
import os
import uuid
from fastapi import Form
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import select, func
import hashlib
import tempfile
import zipfile
import shutil
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager

from graph.connection import get_driver
from etl.bloodhound import ingest_bloodhound as ingest_data
from llm.planner import find_and_score_paths, generate_campaign_plan, find_top_paths_for_engagement

from config import ALLOWED_ORIGINS
from api.auth import (
    get_current_user, require_roles, create_access_token,
    authenticate_user, AuthenticatedUser, PUBLIC_PATHS,
    _get_db_session,
)
from db.ingestion_ops import (
    is_already_ingested as pg_is_already_ingested,
    record_ingestion as pg_record_ingestion,
    get_ingestion_record_by_hash,
    _engine as _ingestion_engine,
)
from api.path_utils import enrich_paths, sort_paths


async def require_engagement_ownership(
    engagement_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> str:
    """
    FastAPI dependency that validates:
    1. engagement_id is a valid UUID
    2. engagement belongs to the user's org_id (tenant isolation)
    Returns the validated engagement_id string on success.
    Raises 422 for missing/invalid UUID, 404 for cross-tenant access.
    """
    if not engagement_id:
        raise HTTPException(status_code=422, detail="engagement_id is required")
    try:
        engagement_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="engagement_id must be a valid UUID")

    # Check ownership in Postgres
    from db.models import Engagement
    with _get_db_session() as db:
        stmt = select(Engagement).where(
            Engagement.id == engagement_uuid,
            Engagement.org_id == uuid.UUID(user.org_id)
        )
        engagement = db.scalar(stmt)
        if not engagement:
            raise HTTPException(status_code=404, detail="Engagement not found for your org")
    return engagement_id


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


class OverviewPath(BaseModel):
    source: str
    target: str
    hops: int
    steps: int
    nodes: List[str]
    rels: List[str]
    score: float | None
    label: str
    source_privileged: bool


class OverviewResponse(BaseModel):
    engagement: Dict[str, str]
    asset_count: int
    relationship_count: int
    top_paths: List[OverviewPath]
    rel_type_breakdown: List[Dict[str, Any]]
    privileged_accounts: int
    recent_ingestion: List[Dict[str, Any]]
    pipeline: Dict[str, Any]

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
        stmt = select(Engagement).where(Engagement.org_id == uuid.UUID(user.org_id)).order_by(Engagement.created_at.desc())
        engagements = session.scalars(stmt).all()
    result = []
    for e in engagements:
        # Basic stats from Neo4j counts
        node_count = 0
        try:
            from graph.connection import get_driver
            async with get_driver().session() as neo:
                res = await neo.run("MATCH (n) WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id RETURN count(n) AS c", org_id=str(user.org_id), engagement_id=str(e.id))
                rec = await res.single()
                if rec:
                    node_count = rec["c"]
        except Exception:
            node_count = 0
        result.append({
            "id": str(e.id),
            "name": e.name,
            "status": e.status.value,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "node_count": node_count,
        })
    return result

class CreateEngagementRequest(BaseModel):
    name: str

class UpdateEngagementRequest(BaseModel):
    name: str
    status: str | None = None

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

@app.patch("/engagements/{engagement_id}")
@limiter.limit("5/minute")
async def update_engagement(engagement_id: str, request: Request, payload: UpdateEngagementRequest, user: AuthenticatedUser = Depends(require_roles("org_admin", "operator"))):
    from db.models import Engagement, EngagementStatus
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    with Session(_ingestion_engine) as session:
        stmt = select(Engagement).where(Engagement.id == uuid.UUID(engagement_id), Engagement.org_id == uuid.UUID(user.org_id))
        eng = session.scalar(stmt)
        if not eng:
            raise HTTPException(status_code=404, detail="Engagement not found")
        eng.name = payload.name
        if payload.status:
            try:
                eng.status = EngagementStatus(payload.status)
            except Exception:
                raise HTTPException(status_code=422, detail="Invalid status")
        session.commit()
        session.refresh(eng)
    return {"id": str(eng.id), "name": eng.name, "status": eng.status.value}

@app.delete("/engagements/{engagement_id}")
@limiter.limit("5/minute")
async def delete_engagement(engagement_id: str, request: Request, user: AuthenticatedUser = Depends(require_roles("org_admin"))):
    from db.models import Engagement, IngestionRecord, Plan
    from sqlalchemy.orm import Session
    from sqlalchemy import select, delete

    try:
        eng_uuid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    with Session(_ingestion_engine) as session:
        stmt = select(Engagement).where(Engagement.id == eng_uuid, Engagement.org_id == uuid.UUID(user.org_id))
        eng = session.scalar(stmt)
        if not eng:
            raise HTTPException(status_code=404, detail="Engagement not found")

        # Delete related Neo4j nodes first to avoid orphan data — do NOT swallow errors!
        try:
            from graph.connection import get_driver
            async with get_driver().session() as neo:
                await neo.run("MATCH (n) WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id DETACH DELETE n", org_id=str(user.org_id), engagement_id=engagement_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Neo4j deletion failed: {e}")

        # Delete plans first
        session.execute(delete(Plan).where(Plan.engagement_id == eng_uuid))
        
        # Delete ingestion records referencing this engagement
        session.execute(delete(IngestionRecord).where(IngestionRecord.engagement_id == eng_uuid))

        # Delete engagement record
        session.delete(eng)
        session.commit()
    return {"detail": "Engagement deleted"}


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
async def graph_stats(
    request: Request,
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        async with get_driver().session() as session:
            node_result = await session.run("""
                MATCH (n)
                WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id
                RETURN labels(n)[0] AS type, count(n) AS count
                ORDER BY count DESC
            """, org_id=user.org_id, engagement_id=engagement_id)
            nodes = {r["type"]: r["count"] async for r in node_result}

            rel_result = await session.run("""
                MATCH (s)-[r]->(t)
                WHERE s.org_id = $org_id AND s.engagement_id = $engagement_id
                  AND t.org_id = $org_id AND t.engagement_id = $engagement_id
                RETURN type(r) AS type, count(r) AS count
                ORDER BY count DESC
            """, org_id=user.org_id, engagement_id=engagement_id)
            relationships = {r["type"]: r["count"] async for r in rel_result}

            return {"nodes": nodes, "relationships": relationships}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/graph/nodes")
@limiter.limit("60/minute")
async def graph_nodes(
    request: Request,
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        async with get_driver().session() as session:
            users_result = await session.run("""
                MATCH (u:User)
                WHERE u.org_id = $org_id AND u.engagement_id = $engagement_id
                RETURN DISTINCT u.name AS name
                ORDER BY u.name
            """, org_id=user.org_id, engagement_id=engagement_id)
            users = [r["name"] async for r in users_result]

            computers_result = await session.run("""
                MATCH (c:Computer)
                WHERE c.org_id = $org_id AND c.engagement_id = $engagement_id
                RETURN DISTINCT c.name AS name
                ORDER BY c.name
            """, org_id=user.org_id, engagement_id=engagement_id)
            computers = [r["name"] async for r in computers_result]

            return {"users": users, "computers": computers}
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
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(get_current_user)
):
    try:
        org_id = str(user.org_id)
        raw_paths = await find_and_score_paths(source, target, org_id=org_id, engagement_id=engagement_id)
        if not raw_paths:
            return []
        async with get_driver().session() as session:
            privileged = False
            r = await session.run(
                "MATCH (u:User) WHERE u.org_id = $org_id AND u.engagement_id = $engagement_id AND (u.name = $src OR u.objectid = $src) AND u.admincount = true RETURN count(u) AS c",
                org_id=org_id, engagement_id=engagement_id, src=source
            )
            rec = await r.single()
            if rec and rec["c"] > 0:
                privileged = True
        # Build a map for enrichment
        src_map = {p.get("source", source): privileged for p in raw_paths}
        # Normalize raw paths to have source/target consistent
        norm_paths = []
        for p in raw_paths:
            norm_paths.append({
                "source": p.get("source", source),
                "target": p.get("target", target),
                "hops": p.get("hops", 0),
                "nodes": p.get("nodes", []),
                "rels": p.get("rels", []),
                "score": p.get("score"),
            })
        enriched = enrich_paths(norm_paths, src_map)
        enriched = sort_paths(enriched)
        return enriched
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"ML stack not available on this instance: {e}. "
                   "Install torch and torch_geometric to enable path scoring.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plan/generate")
@limiter.limit("5/minute")
async def plan_generate(
    request: Request,
    plan_request: PlanRequest,
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(require_roles("org_admin", "operator"))
):
    from db.models import Plan
    from sqlalchemy.orm import Session
    from db.ingestion_ops import _engine
    import json

    org_id = str(user.org_id)

    # 1. Check if source and target nodes exist in Neo4j for this org + engagement
    from graph.connection import get_driver
    async with get_driver().session() as neo:
        r1 = await neo.run(
            "MATCH (n) WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id AND (n.name = $src OR n.objectid = $src) RETURN count(n) AS c",
            org_id=org_id, engagement_id=engagement_id, src=plan_request.source
        )
        rec1 = await r1.single()
        if not rec1 or rec1["c"] == 0:
            raise HTTPException(status_code=404, detail=f"Source node '{plan_request.source}' not found in engagement")

        r2 = await neo.run(
            "MATCH (n) WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id AND (n.name = $dst OR n.objectid = $dst) RETURN count(n) AS c",
            org_id=org_id, engagement_id=engagement_id, dst=plan_request.target
        )
        rec2 = await r2.single()
        if not rec2 or rec2["c"] == 0:
            raise HTTPException(status_code=404, detail=f"Target node '{plan_request.target}' not found in engagement")

    # 2. Check if an attack path exists
    paths = await find_and_score_paths(plan_request.source, plan_request.target, org_id, engagement_id)
    if not paths:
        raise HTTPException(status_code=404, detail=f"No attack path found from '{plan_request.source}' to '{plan_request.target}'")

    # 3. Generate campaign plan
    try:
        plan_res = await generate_campaign_plan(plan_request.source, plan_request.target, org_id=org_id, engagement_id=engagement_id)
        if isinstance(plan_res, dict):
            plan_text = plan_res["plan"]
            actor_name = plan_res["actor_name"]
            used_llm = plan_res["used_llm"]
            rag_used = plan_res["rag_used"]
        else:
            plan_text = str(plan_res)
            actor_name = "unknown"
            used_llm = True
            rag_used = False
    except Exception:
        from llm.planner import _templated_plan
        plan_text = _templated_plan(paths)
        actor_name = "unknown"
        used_llm = False
        rag_used = False

    top_path = paths[0]
    nodes_list = top_path.get("nodes", [])
    rels_list = top_path.get("rels", [])
    path_data = {
        "nodes": nodes_list,
        "rels": rels_list,
        "hops": top_path.get("hops", len(rels_list)),
        "steps": len(rels_list),
        "label": f"{nodes_list[0]} -> {nodes_list[-1]}" if nodes_list else "",
        "score": top_path.get("score"),
        "plan": plan_text,
        "matched_actor": actor_name
    }

    with Session(_engine) as session:
        new_plan = Plan(
            org_id=uuid.UUID(org_id),
            engagement_id=uuid.UUID(engagement_id),
            source=plan_request.source,
            target=plan_request.target,
            rag_used=rag_used,
            used_llm=used_llm,
            path_json=json.dumps(path_data),
            created_at=datetime.utcnow()
        )
        session.add(new_plan)
        session.commit()
        session.refresh(new_plan)

    return {
        "id": str(new_plan.id),
        "plan": plan_text,
        "used_llm": used_llm,
        "rag_used": rag_used,
        "matched_actor": actor_name,
        "timestamp": new_plan.created_at.isoformat()
    }


@app.get("/plans")
@limiter.limit("30/minute")
async def get_plans(
    request: Request,
    engagement_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    from db.models import Plan
    from sqlalchemy.orm import Session
    from db.ingestion_ops import _engine
    
    # Ownership check
    await require_engagement_ownership(engagement_id, user)
    
    with Session(_engine) as session:
        stmt = select(Plan).where(
            Plan.engagement_id == uuid.UUID(engagement_id),
            Plan.org_id == uuid.UUID(user.org_id)
        ).order_by(Plan.created_at.desc())
        plans = session.scalars(stmt).all()
        
    return [
        {
            "id": str(p.id),
            "source": p.source,
            "target": p.target,
            "created_at": p.created_at.isoformat(),
            "rag_used": p.rag_used,
            "used_llm": p.used_llm
        }
        for p in plans
    ]

@app.get("/plans/{plan_id}")
@limiter.limit("30/minute")
async def get_plan(
    plan_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user)
):
    from db.models import Plan
    from sqlalchemy.orm import Session
    from db.ingestion_ops import _engine
    import json

    try:
        pid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid plan_id UUID")

    with Session(_engine) as session:
        plan = session.get(Plan, pid)
        if not plan or plan.org_id != uuid.UUID(user.org_id):
            raise HTTPException(status_code=404, detail="Plan not found")

        try:
            pj = json.loads(plan.path_json)
        except Exception:
            pj = plan.path_json

        return {
            "id": str(plan.id),
            "source": plan.source,
            "target": plan.target,
            "rag_used": plan.rag_used,
            "used_llm": plan.used_llm,
            "path_json": pj,
            "created_at": plan.created_at.isoformat()
        }

async def gnn_status(
    request: Request,
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(get_current_user),
):
    from gnn.init_gat import get_retrain_status
    status = get_retrain_status(str(user.org_id), engagement_id)
    return {"org_id": str(user.org_id), "engagement_id": engagement_id, **status}


@app.get("/overview")
@limiter.limit("30/minute")
async def get_overview(
    request: Request,
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 10
):
    org_id = str(user.org_id)
    
    async with get_driver().session() as session:
        # Engagement name
        from db.models import Engagement
        from sqlalchemy.orm import Session as DBSession
        from sqlalchemy import select
        import uuid as _uuid
        with DBSession(_ingestion_engine) as db:
            stmt = select(Engagement).where(
                Engagement.id == _uuid.UUID(engagement_id),
                Engagement.org_id == _uuid.UUID(org_id)
            )
            eng = db.scalar(stmt)
            engagement_name = eng.name if eng else "Unknown"

        # Asset count (all nodes)
        r = await session.run(
            "MATCH (n) WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id RETURN count(n) AS c",
            org_id=org_id, engagement_id=engagement_id
        )
        rec = await r.single()
        asset_count = rec["c"] if rec else 0

        # Relationship count (via endpoint nodes)
        r = await session.run(
            "MATCH (a)-[r]->(b) WHERE a.org_id = $org_id AND a.engagement_id = $engagement_id AND b.org_id = $org_id AND b.engagement_id = $engagement_id RETURN count(r) AS c",
            org_id=org_id, engagement_id=engagement_id
        )
        rec = await r.single()
        relationship_count = rec["c"] if rec else 0
        
        # Rel type breakdown (top 6 + other)
        r = await session.run(
            "MATCH (a)-[r]->(b) WHERE a.org_id = $org_id AND a.engagement_id = $engagement_id AND b.org_id = $org_id AND b.engagement_id = $engagement_id RETURN type(r) AS rel_type, count(r) AS c ORDER BY c DESC",
            org_id=org_id, engagement_id=engagement_id
        )
        rel_counts = {}
        async for record in r:
            rel_counts[record["rel_type"]] = record["c"]
        total_rels = sum(rel_counts.values())
        top_rels = sorted(rel_counts.items(), key=lambda x: x[1], reverse=True)[:6]
        rel_breakdown = [{"rel_type": k, "count": v} for k, v in top_rels]
        other_count = total_rels - sum(v for _, v in top_rels)
        if other_count > 0:
            rel_breakdown.append({"rel_type": "other", "count": other_count})
        
        # Privileged accounts
        r = await session.run(
            "MATCH (u:User) WHERE u.org_id = $org_id AND u.engagement_id = $engagement_id AND u.admincount = true RETURN count(u) AS c",
            org_id=org_id, engagement_id=engagement_id
        )
        rec = await r.single()
        privileged_accounts = rec["c"] if rec else 0
        
        # Recent ingestion for THIS engagement
        from db.models import IngestionRecord
        from sqlalchemy import select as sql_select
        from sqlalchemy.orm import Session as DBSession
        with DBSession(_ingestion_engine) as db:
            stmt = sql_select(IngestionRecord).where(
                IngestionRecord.org_id == _uuid.UUID(org_id),
                IngestionRecord.engagement_id == _uuid.UUID(engagement_id)
            ).order_by(IngestionRecord.ingested_at.desc()).limit(5)
            records = db.scalars(stmt).all()
        recent_ingestion = [
            {
                "filename": r.filename,
                "status": r.status.value,
                "ingested_at": r.ingested_at.isoformat(),
            }
            for r in records
        ]
        
        # Pipeline info
        last_ingested = recent_ingestion[0]["ingested_at"] if recent_ingestion else None
        # Threat actors check (global)
        r = await session.run("MATCH (a:ThreatActor) RETURN count(a) AS c")
        rec = await r.single()
        threat_actor_count = rec["c"] if rec else 0

        # Plans count
        from db.models import Plan
        with DBSession(_ingestion_engine) as db:
            stmt = sql_select(func.count(Plan.id)).where(
                Plan.org_id == _uuid.UUID(org_id),
                Plan.engagement_id == _uuid.UUID(engagement_id)
            )
            plans_count = db.scalar(stmt) or 0

        pipeline = {
            "ingested": len(recent_ingestion) > 0,
            "last_ingested_at": last_ingested,
            "paths_found": 0,  # will update after paths
            "threat_actors": threat_actor_count > 0,
            "plans_count": plans_count
        }
        
        # Top paths with scoring and classification
        raw_paths = await find_top_paths_for_engagement(org_id, engagement_id, limit=limit * 3)
        
        # Build source_privileged map
        source_privileged_map = {}
        if raw_paths:
            sources = list(set(p["source"] for p in raw_paths))
            for src in sources:
                r = await session.run(
                    "MATCH (u:User) WHERE u.org_id = $org_id AND u.engagement_id = $engagement_id AND (u.name = $src OR u.objectid = $src) AND u.admincount = true RETURN count(u) AS c",
                    org_id=org_id, engagement_id=engagement_id, src=src
                )
                rec = await r.single()
                source_privileged_map[src] = bool(rec and rec["c"] > 0)
        
        enriched_paths = enrich_paths(raw_paths, source_privileged_map)
        enriched_paths = sort_paths(enriched_paths)
        top_paths = enriched_paths[:limit]
        
        pipeline["paths_found"] = len(enriched_paths)
        
        return {
            "engagement": {"id": engagement_id, "name": engagement_name},
            "asset_count": asset_count,
            "relationship_count": relationship_count,
            "top_paths": top_paths,
            "rel_type_breakdown": rel_breakdown,
            "privileged_accounts": privileged_accounts,
            "recent_ingestion": recent_ingestion,
            "pipeline": pipeline
        }


@app.get("/paths/top")
@limiter.limit("30/minute")
async def get_top_paths(
    request: Request,
    engagement_id: str = Depends(require_engagement_ownership),
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 10
):
    try:
        org_id = str(user.org_id)
        raw_paths = await find_top_paths_for_engagement(org_id, engagement_id, limit=limit)
        if not raw_paths:
            return []
        async with get_driver().session() as session:
            source_privileged_map = {}
            sources = list({p["source"] for p in raw_paths})
            for src in sources:
                r = await session.run(
                    "MATCH (u:User) WHERE u.org_id = $org_id AND u.engagement_id = $engagement_id AND (u.name = $src OR u.objectid = $src) AND u.admincount = true RETURN count(u) AS c",
                    org_id=org_id, engagement_id=engagement_id, src=src
                )
                rec = await r.single()
                source_privileged_map[src] = bool(rec and rec["c"] > 0)
        enriched = enrich_paths(raw_paths, source_privileged_map)
        enriched = sort_paths(enriched)
        return enriched
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"ML stack not available on this instance: {e}. "
                   "Install torch and torch_geometric to enable path scoring.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/actors")
@limiter.limit("30/minute")
async def get_actors(request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    try:
        async with get_driver().session() as session:
            result = await session.run(
                "MATCH (a:ThreatActor) OPTIONAL MATCH (a)-[:USES]->(t:Technique) RETURN a.name AS actor_name, a.motivation AS motivation, a.sophistication AS sophistication, collect(DISTINCT t.name) AS techniques"
            )
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
