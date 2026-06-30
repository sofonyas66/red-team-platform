"""
api/main.py — FastAPI application exposing the red team platform pipeline as REST endpoints
"""

import json
import os
import tempfile
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph.connection import driver
from etl.bloodhound import ingest_data
from llm.planner import find_and_score_paths, generate_campaign_plan

app = FastAPI(
    title="Red Team Planning Platform API",
    description="INSA Ethiopia — Automated Attack Path Analysis & Campaign Planning",
    version="1.0.0"
)

# CORS middleware allowing localhost origins (and * for flexibility)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Pydantic Models
# ============================================================================

class PlanRequest(BaseModel):
    source: str
    target: str


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Returns {"status": "ok", "neo4j": true/false} checking if Neo4j is alive."""
    try:
        with driver.session() as session:
            session.run("RETURN 1")
        return {"status": "ok", "neo4j": True}
    except Exception:
        return {"status": "error", "neo4j": False}


@app.get("/graph/stats")
async def graph_stats():
    """Returns node counts and relationship counts (same as demo.py Step 1)."""
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
            
            return {
                "nodes": nodes,
                "relationships": relationships
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/bloodhound")
async def upload_bloodhound(file: UploadFile = File(...)):
    """Accepts a JSON file upload, runs etl/bloodhound.py logic, returns counts."""
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="File must be a JSON file")
        
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp:
        content = await file.read()
        tmp.write(content.decode('utf-8'))
        tmp_path = tmp.name

    try:
        # Run ingestion
        ingest_data(tmp_path)
        
        # Count what was ingested
        with driver.session() as session:
            node_count = session.run("MATCH (n) WHERE n.source = 'bloodhound' RETURN count(n) AS count").single()["count"]
            rel_count = session.run("MATCH ()-[r]->() WHERE r.source = 'bloodhound' RETURN count(r) AS count").single()["count"]
            
        return {
            "status": "success",
            "nodes_ingested": node_count,
            "relationships_ingested": rel_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/paths")
async def get_paths(source: str, target: str):
    """Runs path scoring and returns ranked paths as JSON."""
    try:
        paths = find_and_score_paths(source, target)
        return paths
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/plan/generate")
async def plan_generate(request: PlanRequest):
    """Runs the full campaign planning pipeline and returns the plan text."""
    try:
        plan_text = generate_campaign_plan(request.source, request.target)
        return {"plan": plan_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/actors")
async def get_actors():
    """Returns all ThreatActor nodes from ETI-Core with their techniques."""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)