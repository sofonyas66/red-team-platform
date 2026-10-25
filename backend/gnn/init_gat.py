#!/usr/bin/env python3
"""
gnn/init_gat.py — Per-tenant GAT model initialization, caching, and background retraining.

Cache layout on disk:
    gnn/cache/{org_id}/{engagement_id}/path_gat.pt
    gnn/cache/{org_id}/{engagement_id}/graph_tensors.pt
    gnn/cache/{org_id}/{engagement_id}/metadata.json   # trained_at, node/edge counts, status

In-memory: bounded LRU OrderedDict keyed by (org_id, engagement_id).
    Evictions only remove the hot in-memory copy — disk cache persists.

torch and torch_geometric are imported lazily (inside functions that need them)
so this module can be imported without the ML stack.
"""
import json
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from gnn.model import (
    EDGE_TYPES, EDGE_TYPE_TO_ID, EDGE_SEVERITY,
    get_path_gat_class, train_gat, score_path,
)

# ── Disk cache root ────────────────────────────────────────────────────────
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# ── In-memory LRU cache (bounded) ─────────────────────────────────────────
_MAX_CACHED_MODELS_IN_MEMORY = 5   # tune based on available RAM
_gat_state_cache: "OrderedDict[tuple[str, str], dict]" = OrderedDict()
_cache_lock = threading.Lock()

# ── Background retraining status ──────────────────────────────────────────
# Simple in-memory tracker.
# LIMITATION: status is lost on process restart.  A future pass should
# persist this in the `ingestion_records` Postgres table.
_retrain_status: dict[tuple[str, str], dict] = {}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _tenant_cache_dir(org_id: str, engagement_id: str) -> Path:
    d = CACHE_DIR / org_id / engagement_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(org_id: str, engagement_id: str) -> tuple[str, str]:
    return (org_id, engagement_id)


# ═══════════════════════════════════════════════════════════════════════════
# Graph data loading (async, tenant-scoped)
# ═══════════════════════════════════════════════════════════════════════════

async def load_graph_data(org_id: str, engagement_id: str):
    """
    Load node embeddings and relationships from Neo4j scoped to one tenant+engagement.
    Uses TenantSession so every query carries $org_id / $engagement_id.
    """
    from graph.tenant_session import TenantSession

    node_names: list[str] = []
    node_embeddings: list = []
    node_types: list[str] = []
    edges: list[dict] = []

    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        emb_result = await ts.run("""
            MATCH (n)
            WHERE n.embedding IS NOT NULL AND n.org_id = $org_id AND n.engagement_id = $engagement_id
            RETURN
                coalesce(n.name, n.objectid, n.actor_id, n.technique_id) AS name,
                n.embedding AS embedding,
                labels(n)[0] AS node_type
        """)
        async for record in emb_result:
            node_names.append(record["name"])
            node_embeddings.append(record["embedding"])
            node_types.append(record["node_type"])

        rel_result = await ts.run("""
            MATCH (a)-[r]->(b)
            WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
              AND a.org_id = $org_id AND a.engagement_id = $engagement_id
              AND b.org_id = $org_id AND b.engagement_id = $engagement_id
            RETURN
                coalesce(a.name, a.objectid, a.actor_id, a.technique_id) AS src,
                coalesce(b.name, b.objectid, b.actor_id, b.technique_id) AS dst,
                type(r) AS rel_type
        """)
        async for record in rel_result:
            edges.append({
                "src": record["src"],
                "dst": record["dst"],
                "type": record["rel_type"],
            })

    return node_names, node_embeddings, node_types, edges


# ═══════════════════════════════════════════════════════════════════════════
# Tensor building
# ═══════════════════════════════════════════════════════════════════════════

def build_tensors(node_names, node_embeddings, edges):
    """Build PyG-compatible tensors from raw graph data."""
    import torch  # lazy

    name_to_idx = {name: i for i, name in enumerate(node_names)}

    edge_src, edge_dst, edge_type_ids, edge_type_names = [], [], [], []
    for edge in edges:
        s, d, rt = edge["src"], edge["dst"], edge["type"]
        if s in name_to_idx and d in name_to_idx:
            edge_src.append(name_to_idx[s])
            edge_dst.append(name_to_idx[d])
            edge_type_ids.append(EDGE_TYPE_TO_ID.get(rt, 0))
            edge_type_names.append(rt)

    x = torch.tensor(node_embeddings, dtype=torch.float)
    if x.shape[1] < 128:
        pad = torch.zeros(x.shape[0], 128 - x.shape[1])
        x = torch.cat([x, pad], dim=1)

    edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long)
    edge_type = torch.tensor(edge_type_ids, dtype=torch.long)

    return x, edge_index, edge_type, edge_type_names, name_to_idx


# ═══════════════════════════════════════════════════════════════════════════
# initialize_gat — load from disk cache or train fresh
# ═══════════════════════════════════════════════════════════════════════════

async def initialize_gat(
    org_id: str,
    engagement_id: str,
    force_retrain: bool = False,
    gat_epochs: int = 200,
) -> dict:
    """
    Return a state dict for the given tenant+engagement.

    State dict keys:
        model, x, edge_index, edge_type, edge_type_names, name_to_idx

    If a disk cache exists and force_retrain is False, loads from disk.
    Otherwise trains fresh against Neo4j data and writes to disk.
    """
    import torch  # lazy

    PathGAT = get_path_gat_class()
    cache_dir = _tenant_cache_dir(org_id, engagement_id)
    model_path = cache_dir / "path_gat.pt"
    tensors_path = cache_dir / "graph_tensors.pt"
    mapping_path = cache_dir / "node_mapping.json"
    meta_path = cache_dir / "metadata.json"

    if not force_retrain and model_path.exists() and tensors_path.exists() and mapping_path.exists():
        print(f"[GAT] Loading cached model for {org_id}/{engagement_id} ...")
        x, edge_index, edge_type, edge_type_names = torch.load(
            tensors_path, map_location="cpu", weights_only=False
        )
        name_to_idx = json.loads(mapping_path.read_text())
        model = PathGAT()
        model.load_state_dict(
            torch.load(model_path, map_location="cpu", weights_only=True)
        )
        model.eval()
        return dict(
            model=model, x=x, edge_index=edge_index,
            edge_type=edge_type, edge_type_names=edge_type_names,
            name_to_idx=name_to_idx,
        )

    print(f"[GAT] Training fresh model for {org_id}/{engagement_id} ...")
    node_names, node_embeddings, node_types, edges = await load_graph_data(
        org_id, engagement_id
    )
    print(f"  Nodes with embeddings: {len(node_names)}")
    print(f"  Relationships: {len(edges)}")

    if not node_names:
        raise RuntimeError(
            f"No embedded nodes found for org={org_id} engagement={engagement_id}. "
            "Run gnn/embeddings.py first."
        )

    x, edge_index, edge_type, edge_type_names, name_to_idx = build_tensors(
        node_names, node_embeddings, edges
    )
    print(f"  x={x.shape}, edge_index={edge_index.shape}, edge_type={edge_type.shape}")

    model = PathGAT()
    model = train_gat(model, x, edge_index, edge_type, edge_type_names, epochs=gat_epochs)

    # Persist to disk
    torch.save(model.state_dict(), model_path)
    torch.save((x, edge_index, edge_type, edge_type_names), tensors_path)
    mapping_path.write_text(json.dumps(name_to_idx))
    meta_path.write_text(json.dumps({
        "trained_at": datetime.utcnow().isoformat(),
        "node_count": len(node_names),
        "edge_count": len(edges),
        "status": "ready",
    }))
    print(f"  Cached to {cache_dir}")

    return dict(
        model=model, x=x, edge_index=edge_index,
        edge_type=edge_type, edge_type_names=edge_type_names,
        name_to_idx=name_to_idx,
    )


# ═══════════════════════════════════════════════════════════════════════════
# In-memory LRU cache API
# ═══════════════════════════════════════════════════════════════════════════

async def get_gat_state(org_id: str, engagement_id: str) -> dict:
    """
    Return the GAT state for this tenant+engagement, from in-memory LRU cache
    or by loading/training on demand.
    """
    key = _cache_key(org_id, engagement_id)

    with _cache_lock:
        if key in _gat_state_cache:
            _gat_state_cache.move_to_end(key)  # LRU touch
            return _gat_state_cache[key]

    # Load/train outside the lock (can be slow)
    state = await initialize_gat(org_id, engagement_id)

    with _cache_lock:
        _gat_state_cache[key] = state
        _gat_state_cache.move_to_end(key)
        while len(_gat_state_cache) > _MAX_CACHED_MODELS_IN_MEMORY:
            evicted_key, _ = _gat_state_cache.popitem(last=False)
            print(f"[GAT] LRU eviction: {evicted_key} (disk cache untouched)")

    return state


def invalidate_gat_state(org_id: str, engagement_id: str):
    """
    Clear in-memory AND on-disk cache for one tenant+engagement.
    Called after re-ingestion so the next call to get_gat_state() retrains.
    Only invalidates the specified tenant — other tenants are not affected.
    """
    key = _cache_key(org_id, engagement_id)
    with _cache_lock:
        _gat_state_cache.pop(key, None)

    cache_dir = CACHE_DIR / org_id / engagement_id
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)
        print(f"[GAT] Invalidated cache for {org_id}/{engagement_id}")


# ═══════════════════════════════════════════════════════════════════════════
# Background retraining
# ═══════════════════════════════════════════════════════════════════════════

async def retrain_gat_background(org_id: str, engagement_id: str):
    """
    Async background task called by FastAPI BackgroundTasks.

    FastAPI (≥0.51, confirmed on 0.141.1 pinned here) natively awaits async
    background callables on the *same* event loop as the request handler.
    This means the AsyncGraphDatabase driver (bound to FastAPI's loop at import
    time in graph/connection.py) is reachable without a loop mismatch.

    The previous `def` + `asyncio.run()` implementation spun up a *new* event
    loop, causing:
        got Future <Future pending> attached to a different loop
    because the driver's internal futures were owned by the main loop.

    This version keeps all Neo4j async calls (via TenantSession) on the main
    event loop, and only offloads the CPU-bound torch Node2Vec training
    to a thread via asyncio.to_thread.

    Status is tracked in _retrain_status (in-memory only — not crash-safe).
    """
    import asyncio
    import os
    from gnn.embeddings import fetch_graph_from_neo4j, run_node2vec, store_embeddings_in_neo4j, build_pyg_data
    import torch

    # Limit torch intra-op parallelism to avoid oversubscribing on no-AVX2 CPUs
    # Use a fixed smaller number (half of logical cores, min 2) rather than os.cpu_count()
    # which would use all cores and cause contention / thrashing on this hardware.
    try:
        cpu_count = os.cpu_count() or 2
        torch_threads = max(2, cpu_count // 2)
        torch.set_num_threads(torch_threads)
        print(f"[GAT] Set torch.set_num_threads({torch_threads}) (CPU count: {cpu_count})")
    except Exception as e:
        print(f"[GAT] Warning: could not set torch thread limit: {e}")

    # Fast train mode via env var (demo only, default OFF)
    fast_train = os.environ.get("RTAP_FAST_TRAIN") == "1"
    if fast_train:
        print("[GAT] FAST TRAIN MODE (env RTAP_FAST_TRAIN=1) -- reduced quality, for demo use only")
        n2v_num_walks = 20
        n2v_walk_length = 10
        n2v_epochs = 4
        gat_epochs = 60
    else:
        n2v_num_walks = 80
        n2v_walk_length = 20
        n2v_epochs = 8
        gat_epochs = 200

    key = (org_id, engagement_id)
    _retrain_status[key] = {
        "status": "training",
        "started_at": datetime.utcnow().isoformat(),
    }
    try:
        # Step 1: Generate Node2Vec embeddings
        # 1a: Fetch graph from Neo4j (async, stays on main loop)
        print(f"[GAT] Fetching graph for {org_id}/{engagement_id}...")
        G, node_to_idx, idx_to_node = await fetch_graph_from_neo4j(org_id, engagement_id)
        
        if G.number_of_nodes() == 0:
            raise RuntimeError(
                f"No nodes found for org={org_id} engagement={engagement_id}. "
                "Run ETL first."
            )
        print(f"[GAT] Fetched {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        # 1b: Build PyG data (sync, fast)
        data = build_pyg_data(G, node_to_idx)

        # 1c: Run Node2Vec (CPU-bound torch, offload to thread)
        print(f"[GAT] Running Node2Vec for {org_id}/{engagement_id} (walks={n2v_num_walks}, walk_len={n2v_walk_length}, epochs={n2v_epochs})...")
        embeddings = await asyncio.to_thread(
            run_node2vec, data,
            n2v_num_walks, n2v_walk_length, n2v_epochs
        )
        print(f"[GAT] Node2Vec complete for {org_id}/{engagement_id}")

        # 1d: Store embeddings back to Neo4j (async, stays on main loop)
        print(f"[GAT] Storing embeddings for {org_id}/{engagement_id}...")
        await store_embeddings_in_neo4j(embeddings, idx_to_node, org_id, engagement_id)
        print(f"[GAT] Embeddings stored for {org_id}/{engagement_id}")

        # Step 2: Train GAT on embedded graph
        state = await initialize_gat(org_id, engagement_id, force_retrain=True, gat_epochs=gat_epochs)
        with _cache_lock:
            _gat_state_cache[key] = state
            _gat_state_cache.move_to_end(key)
            while len(_gat_state_cache) > _MAX_CACHED_MODELS_IN_MEMORY:
                _gat_state_cache.popitem(last=False)
        _retrain_status[key] = {
            "status": "ready",
            "completed_at": datetime.utcnow().isoformat(),
        }
        print(f"[GAT] Background retraining complete for {org_id}/{engagement_id}")
    except Exception as exc:
        _retrain_status[key] = {
            "status": "failed",
            "error": str(exc),
            "failed_at": datetime.utcnow().isoformat(),
        }
        print(f"[GAT] Background retraining FAILED for {org_id}/{engagement_id}: {exc}")


def get_retrain_status(org_id: str, engagement_id: str) -> dict:
    """Return the current retraining status for the given tenant+engagement.

    Priority:
    1. In-memory _retrain_status entry (covers "training" / "failed" / "ready").
    2. If no in-memory entry, check disk cache (model_path, tensors_path, mapping_path).
       If all three exist, treat as "ready" (model already trained and cached).
    3. Otherwise "not_started".

    Returns status plus node_count, edge_count, trained_at from metadata.json when available."""
    key = (org_id, engagement_id)
    cache_dir = CACHE_DIR / org_id / engagement_id
    meta_path = cache_dir / "metadata.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}
    if key in _retrain_status:
        status_data = dict(_retrain_status[key])
        # Merge metadata fields if present
        for k in ("node_count", "edge_count", "trained_at"):
            if k in meta and k not in status_data:
                status_data[k] = meta.get(k)
        return status_data
    # No in-memory entry — check disk cache
    model_path = cache_dir / "path_gat.pt"
    tensors_path = cache_dir / "graph_tensors.pt"
    mapping_path = cache_dir / "node_mapping.json"
    if model_path.exists() and tensors_path.exists() and mapping_path.exists():
        result = {"status": "ready"}
        for k in ("node_count", "edge_count", "trained_at"):
            if k in meta:
                result[k] = meta.get(k)
        return result
    return {"status": "not_started"}


# ═══════════════════════════════════════════════════════════════════════════
# Path scoring
# ═══════════════════════════════════════════════════════════════════════════

async def score_candidate_path(
    path_nodes: list[str],
    path_rels: list[str],
    org_id: str,
    engagement_id: str,
) -> float:
    """Score a single candidate attack path using the per-tenant trained GAT."""
    state = await get_gat_state(org_id, engagement_id)
    model = state["model"]
    x = state["x"]
    edge_index = state["edge_index"]
    edge_type = state["edge_type"]
    edge_type_names = state["edge_type_names"]
    name_to_idx = state["name_to_idx"]

    path_edge_indices = []
    for i in range(len(path_nodes) - 1):
        src_name = path_nodes[i]
        dst_name = path_nodes[i + 1]
        rel_type = path_rels[i]

        if src_name in name_to_idx and dst_name in name_to_idx:
            src_idx = name_to_idx[src_name]
            dst_idx = name_to_idx[dst_name]

            matches = (edge_index[0] == src_idx) & (edge_index[1] == dst_idx)
            match_indices = matches.nonzero(as_tuple=True)[0]

            if len(match_indices) > 0:
                for idx in match_indices:
                    if edge_type_names[idx] == rel_type:
                        path_edge_indices.append(idx.item())
                        break
                else:
                    path_edge_indices.append(match_indices[0].item())

    if not path_edge_indices:
        return 0.0

    return score_path(model, x, edge_index, edge_type, path_edge_indices)


if __name__ == "__main__":
    import asyncio

    async def _main():
        import os
        org_id = os.getenv("TEST_ORG_ID", "test-org")
        engagement_id = os.getenv("TEST_ENGAGEMENT_ID", "test-eng")
        state = await initialize_gat(org_id, engagement_id)
        model = state["model"]
        print("GAT initialized successfully!")
        print(f"  Model params: {sum(p.numel() for p in model.parameters())}")
        print(f"  Nodes: {len(state['name_to_idx'])}")
        print(f"  Edges: {state['edge_index'].shape[1]}")

    asyncio.run(_main())