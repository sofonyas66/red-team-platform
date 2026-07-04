#!/usr/bin/env python3
"""
gnn/init_gat.py — Initialize and cache the PathGAT model with graph data.

Run once at startup to:
1. Load all node embeddings from Neo4j
2. Build edge_index, edge_type tensors from all relationships
3. Train PathGAT using domain-informed edge severity
4. Cache model weights + tensors to disk for fast subsequent loads
"""
import os
import json
import torch
import numpy as np
from pathlib import Path

from graph.connection import driver
from gnn.model import (
    PathGAT, EDGE_TYPES, EDGE_TYPE_TO_ID, EDGE_SEVERITY,
    train_gat, score_path
)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

MODEL_PATH = CACHE_DIR / "path_gat.pt"
TENSORS_PATH = CACHE_DIR / "graph_tensors.pt"
MAPPING_PATH = CACHE_DIR / "node_mapping.json"


def load_graph_data():
    """Load node embeddings and all relationships from Neo4j."""
    with driver.session() as session:
        # Load embeddings
        emb_result = session.run("""
            MATCH (n) WHERE n.embedding IS NOT NULL
            RETURN 
                coalesce(n.name, n.objectid, n.actor_id, n.technique_id) AS name,
                n.embedding AS embedding,
                labels(n)[0] AS node_type
        """)
        
        node_names = []
        node_embeddings = []
        node_types = []
        
        for record in emb_result:
            node_names.append(record["name"])
            node_embeddings.append(record["embedding"])
            node_types.append(record["node_type"])
        
        # Load ALL relationships for GAT training
        rel_result = session.run("""
            MATCH (a)-[r]->(b)
            WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
            RETURN 
                coalesce(a.name, a.objectid, a.actor_id, a.technique_id) AS src,
                coalesce(b.name, b.objectid, b.actor_id, b.technique_id) AS dst,
                type(r) AS rel_type
        """)
        
        edges = []
        for record in rel_result:
            edges.append({
                "src": record["src"],
                "dst": record["dst"],
                "type": record["rel_type"]
            })
    
    return node_names, node_embeddings, node_types, edges


def build_tensors(node_names, node_embeddings, edges):
    """Build PyG-compatible tensors from graph data."""
    name_to_idx = {name: i for i, name in enumerate(node_names)}
    
    edge_src = []
    edge_dst = []
    edge_type_ids = []
    edge_type_names = []
    
    for edge in edges:
        src_name = edge["src"]
        dst_name = edge["dst"]
        rel_type = edge["type"]
        
        if src_name in name_to_idx and dst_name in name_to_idx:
            edge_src.append(name_to_idx[src_name])
            edge_dst.append(name_to_idx[dst_name])
            edge_type_ids.append(EDGE_TYPE_TO_ID.get(rel_type, 0))
            edge_type_names.append(rel_type)
    
    # Node features: 128-dim Node2Vec embeddings (zero-pad for nodes without)
    x = torch.tensor(node_embeddings, dtype=torch.float)
    if x.shape[1] < 128:
        pad = torch.zeros(x.shape[0], 128 - x.shape[1])
        x = torch.cat([x, pad], dim=1)
    
    edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long)
    edge_type = torch.tensor(edge_type_ids, dtype=torch.long)
    
    return x, edge_index, edge_type, edge_type_names, name_to_idx


def initialize_gat():
    """Initialize or load cached PathGAT model."""
    # Check cache
    if MODEL_PATH.exists() and TENSORS_PATH.exists() and MAPPING_PATH.exists():
        print("[GAT] Loading cached model...")
        x, edge_index, edge_type, edge_type_names = torch.load(TENSORS_PATH)
        name_to_idx = json.loads(MAPPING_PATH.read_text())
        
        model = PathGAT()
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        model.eval()
        
        return model, x, edge_index, edge_type, edge_type_names, name_to_idx
    
    print("[GAT] Initializing fresh model from Neo4j...")
    node_names, node_embeddings, node_types, edges = load_graph_data()
    print(f"  Nodes with embeddings: {len(node_names)}")
    print(f"  Relationships: {len(edges)}")
    
    x, edge_index, edge_type, edge_type_names, name_to_idx = build_tensors(
        node_names, node_embeddings, edges
    )
    print(f"  Tensor shapes: x={x.shape}, edge_index={edge_index.shape}, edge_type={edge_type.shape}")
    
    model = PathGAT()
    model = train_gat(model, x, edge_index, edge_type, edge_type_names)
    
    # Cache everything
    torch.save(model.state_dict(), MODEL_PATH)
    torch.save((x, edge_index, edge_type, edge_type_names), TENSORS_PATH)
    MAPPING_PATH.write_text(json.dumps(name_to_idx))
    print(f"  Cached to {CACHE_DIR}")
    
    return model, x, edge_index, edge_type, edge_type_names, name_to_idx


# Global singleton
_GAT_STATE = None

def get_gat_state():
    """Get or initialize the global GAT state."""
    global _GAT_STATE
    if _GAT_STATE is None:
        _GAT_STATE = initialize_gat()
    return _GAT_STATE


def score_candidate_path(path_nodes, path_rels, name_to_idx):
    """Score a single candidate path using the trained GAT."""
    model, x, edge_index, edge_type, edge_type_names, _ = get_gat_state()
    
    # Map path edges to global edge indices
    path_edge_indices = []
    for i in range(len(path_nodes) - 1):
        src_name = path_nodes[i]
        dst_name = path_nodes[i + 1]
        rel_type = path_rels[i]
        
        if src_name in name_to_idx and dst_name in name_to_idx:
            src_idx = name_to_idx[src_name]
            dst_idx = name_to_idx[dst_name]
            
            # Find matching edge in global edge_index
            matches = (edge_index[0] == src_idx) & (edge_index[1] == dst_idx)
            match_indices = matches.nonzero(as_tuple=True)[0]
            
            if len(match_indices) > 0:
                # Prefer edge with matching rel_type
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
    # Test initialization
    model, x, edge_index, edge_type, edge_type_names, name_to_idx = initialize_gat()
    print(f"GAT initialized successfully!")
    print(f"  Model params: {sum(p.numel() for p in model.parameters())}")
    print(f"  Nodes: {len(name_to_idx)}")
    print(f"  Edges: {edge_index.shape[1]}")