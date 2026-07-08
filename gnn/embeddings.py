#!/usr/bin/env python3
"""
gnn/embeddings.py — Generate Node2Vec embeddings for the knowledge graph

Uses PyTorch Geometric's Node2Vec (compatible with existing torch/torch-geometric install).
Pulls the full graph from Neo4j, builds a PyG Data object, runs Node2Vec
to generate 128-dim embeddings for every node, stores embeddings back
as node properties in Neo4j.

Run: python gnn/embeddings.py
"""

import torch
import torch.nn.functional as F
from torch_geometric.nn import Node2Vec
from torch_geometric.data import Data
from graph.connection import driver
import networkx as nx


def fetch_graph_from_neo4j():
    """Pull all nodes and relationships from Neo4j and build a NetworkX graph."""
    print("Fetching graph from Neo4j...")
    
    G = nx.Graph()
    node_to_idx = {}
    idx_to_node = {}
    
    with driver.session() as session:
        # Get all nodes with their appropriate ID field
        nodes_result = session.run("""
            MATCH (n)
            RETURN 
                CASE 
                    WHEN n.objectid IS NOT NULL THEN n.objectid
                    WHEN n.actor_id IS NOT NULL THEN n.actor_id
                    WHEN n.technique_id IS NOT NULL THEN n.technique_id
                    ELSE n.name
                END AS objectid,
                labels(n) AS labels,
                n.name AS name
        """)
        
        node_count = 0
        for record in nodes_result:
            objectid = record["objectid"]
            labels = record["labels"]
            name = record["name"]
            
            if objectid is None:
                continue
                
            G.add_node(objectid, labels=labels, name=name)
            node_to_idx[objectid] = node_count
            idx_to_node[node_count] = objectid
            node_count += 1
        
        print(f"  Nodes loaded: {node_count}")
        
        # Get all relationships
        rels_result = session.run("""
            MATCH (s)-[r]->(t)
            RETURN 
                CASE 
                    WHEN s.objectid IS NOT NULL THEN s.objectid
                    WHEN s.actor_id IS NOT NULL THEN s.actor_id
                    WHEN s.technique_id IS NOT NULL THEN s.technique_id
                    ELSE s.name
                END AS source,
                CASE 
                    WHEN t.objectid IS NOT NULL THEN t.objectid
                    WHEN t.actor_id IS NOT NULL THEN t.actor_id
                    WHEN t.technique_id IS NOT NULL THEN t.technique_id
                    ELSE t.name
                END AS target,
                type(r) AS rel_type
        """)
        
        rel_count = 0
        for record in rels_result:
            source = record["source"]
            target = record["target"]
            rel_type = record["rel_type"]
            
            if source in G and target in G:
                G.add_edge(source, target, rel_type=rel_type)
                rel_count += 1
        
        print(f"  Relationships loaded: {rel_count}")
    
    return G, node_to_idx, idx_to_node


def build_pyg_data(G, node_to_idx):
    """Convert NetworkX graph to PyTorch Geometric Data object."""
    print("Building PyG Data object...")
    
    num_nodes = G.number_of_nodes()
    edge_list = []
    
    for u, v in G.edges():
        u_idx = node_to_idx[u]
        v_idx = node_to_idx[v]
        edge_list.append([u_idx, v_idx])
        edge_list.append([v_idx, u_idx])  # undirected
    
    edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
    
    data = Data(edge_index=edge_index, num_nodes=num_nodes)
    print(f"  Nodes: {num_nodes}, Edges: {edge_index.size(1)}")
    
    return data


def run_node2vec(data, dimensions=128, walk_length=20, num_walks=80,
                 p=1.0, q=1.0, batch_size=256, epochs=8, lr=0.01):
    """Train Node2Vec using PyTorch Geometric."""
    print(f"Running Node2Vec (dimensions={dimensions}, walk_length={walk_length}, "
          f"num_walks={num_walks}, epochs={epochs})...")
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  Using device: {device}")
    
    model = Node2Vec(
        data.edge_index,
        embedding_dim=dimensions,
        walk_length=walk_length,
        context_size=8,
        walks_per_node=num_walks,
        num_negative_samples=3,
        p=p,
        q=q,
        sparse=True
    ).to(device)
    
    data = data.to(device)
    
    loader = model.loader(batch_size=batch_size, shuffle=True, num_workers=0)
    optimizer = torch.optim.SparseAdam(list(model.parameters()), lr=lr)
    
    model.train()
    for epoch in range(1, epochs + 1):
        total_loss = 0
        for pos_rw, neg_rw in loader:
            optimizer.zero_grad()
            loss = model.loss(pos_rw.to(device), neg_rw.to(device))
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        
        if epoch % 1 == 0 or epoch == 1 or epoch == epochs:
            print(f"  Epoch {epoch:3d}/{epochs} — Loss: {total_loss:.4f}")
    
    # Get embeddings for all nodes
    model.eval()
    with torch.no_grad():
        embeddings = model(torch.arange(data.num_nodes, device=device))
    
    return embeddings.cpu()


def store_embeddings_in_neo4j(embeddings, idx_to_node, dimensions=128):
    """Store the learned embeddings back to Neo4j as node properties."""
    print("Storing embeddings in Neo4j...")
    
    batch = []
    for idx in range(embeddings.size(0)):
        objectid = idx_to_node[idx]
        embedding = embeddings[idx].tolist()
        batch.append({
            "objectid": objectid,
            "embedding": embedding
        })
    
    with driver.session() as session:
        batch_size = 500
        updated = 0
        
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            
            query = """
            UNWIND $batch AS item
            MATCH (n)
            WHERE 
                n.objectid = item.objectid 
                OR n.actor_id = item.objectid 
                OR n.technique_id = item.objectid 
                OR n.name = item.objectid
            SET n.embedding = item.embedding,
                n.embedding_dim = $dimensions
            """
            
            session.run(query, batch=chunk, dimensions=dimensions)
            updated += len(chunk)
            print(f"  Updated {updated}/{len(batch)} nodes...")
        
        print(f"  All {updated} embeddings stored")


def main():
    print("=" * 60)
    print("GNN Embeddings Generation — PyG Node2Vec")
    print("=" * 60)
    
    # 1. Fetch graph from Neo4j
    G, node_to_idx, idx_to_node = fetch_graph_from_neo4j()
    
    if G.number_of_nodes() == 0:
        print("ERROR: No nodes found in graph. Run ETL first.")
        return
    
    # 2. Build PyG Data
    data = build_pyg_data(G, node_to_idx)
    
    # 3. Run Node2Vec
    embeddings = run_node2vec(data)
    
    # 4. Store embeddings back to Neo4j
    store_embeddings_in_neo4j(embeddings, idx_to_node)
    
    print("\n" + "=" * 60)
    print("Embeddings generation complete!")
    print("=" * 60)
    
    # Quick verification
    with driver.session() as session:
        result = session.run("""
            MATCH (n) 
            WHERE n.embedding IS NOT NULL 
            RETURN count(n) AS count, size(n.embedding) AS dim
        """)
        record = result.single()
        print(f"Verification: {record['count']} nodes have {record['dim']}-dim embeddings")


if __name__ == "__main__":
    main()
