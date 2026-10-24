#!/usr/bin/env python3
"""
gnn/embeddings.py — Generate Node2Vec embeddings for the knowledge graph

Uses PyTorch Geometric's Node2Vec (compatible with existing torch/torch-geometric install).
Pulls the tenant-scoped graph from Neo4j, builds a PyG Data object, runs Node2Vec
to generate 128-dim embeddings for every node, stores embeddings back
as node properties in Neo4j.

Run: python gnn/embeddings.py --org_id <ORG_ID> --engagement_id <ENGAGEMENT_ID>
"""

import argparse
import asyncio
import torch
import torch.nn.functional as F
import networkx as nx

from graph.tenant_session import TenantSession


async def fetch_graph_from_neo4j(org_id: str, engagement_id: str):
    """Pull all nodes and relationships from Neo4j scoped to one tenant+engagement and build a NetworkX graph."""
    print(f"Fetching graph from Neo4j for org={org_id}, engagement={engagement_id}...")
    
    G = nx.Graph()
    node_to_idx = {}
    idx_to_node = {}
    
    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        # Get all nodes with their appropriate ID field
        nodes_result = await ts.run("""
            MATCH (n)
            WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id
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
        async for record in nodes_result:
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
        
        # Get all relationships - scoped to same tenant+engagement on both ends
        rels_result = await ts.run("""
            MATCH (s)-[r]->(t)
            WHERE s.org_id = $org_id AND s.engagement_id = $engagement_id
              AND t.org_id = $org_id AND t.engagement_id = $engagement_id
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
        async for record in rels_result:
            source = record["source"]
            target = record["target"]
            rel_type = record["rel_type"]
            
            if source in G and target in G:
                G.add_edge(source, target, rel_type=rel_type)
                rel_count += 1
        
        print(f"  Relationships loaded: {rel_count}")
    
    return G, node_to_idx, idx_to_node


def build_pyg_data(G, node_to_idx):
    """Convert NetworkX graph to simple data object with edge_index and num_nodes."""
    print("Building PyG-style Data object...")
    
    num_nodes = G.number_of_nodes()
    edge_list = []
    
    for u, v in G.edges():
        u_idx = node_to_idx[u]
        v_idx = node_to_idx[v]
        edge_list.append([u_idx, v_idx])
        edge_list.append([v_idx, u_idx])  # undirected
    
    edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
    
    class SimpleData:
        pass
    data = SimpleData()
    data.edge_index = edge_index
    data.num_nodes = num_nodes
    print(f"  Nodes: {num_nodes}, Edges: {edge_index.size(1)}")
    return data


def run_node2vec(data, num_walks=None, walk_length=None, epochs=None,
                 dimensions=128, p=1.0, q=1.0, batch_size=256, lr=0.01):
    """Train Node2Vec using PyTorch Geometric.
    
    If num_walks/walk_length/epochs are None, uses production defaults (80, 20, 8).
    """
    if num_walks is None:
        num_walks = 80
    if walk_length is None:
        walk_length = 20
    if epochs is None:
        epochs = 8
    print(f"Running Node2Vec (dimensions={dimensions}, walk_length={walk_length}, "
          f"num_walks={num_walks}, epochs={epochs})...")
    
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  Using device: {device}")
    
    # Pure-PyTorch Node2Vec (DeepWalk-style uniform walks, skip-gram with neg sampling)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    num_nodes = data.num_nodes
    edge_index = data.edge_index
    adj = [[] for _ in range(num_nodes)]
    for i in range(edge_index.size(1)):
        u = edge_index[0, i].item(); v = edge_index[1, i].item()
        adj[u].append(v)
    
    # Random walks (uniform, p=q=1)
    walks = []
    for _ in range(num_walks):
        for node in range(num_nodes):
            walk = [node]
            for _ in range(walk_length - 1):
                neighs = adj[walk[-1]]
                if not neighs: break
                walk.append(neighs[int(torch.randint(len(neighs), (1,)).item())])
            walks.append(walk)
    
    context_size = 8
    print("  Walks generated, building pairs...")
    # Build all positive (center, context) pairs across all walks, once
    pairs = []
    for widx, walk in enumerate(walks):
        if widx % 2000 == 0 and widx > 0:
            print(f"    pair-building progress: {widx}/{len(walks)} walks, {len(pairs)} pairs so far")
        for i, node in enumerate(walk):
            start = max(0, i - context_size)
            end = min(len(walk), i + context_size + 1)
            for j in range(start, end):
                if i == j:
                    continue
                pairs.append((node, walk[j]))

    pairs = torch.tensor(pairs, dtype=torch.long, device=device)  # [P, 2]
    print(f"  Total training pairs: {pairs.size(0)}")

    emb_table = torch.nn.Embedding(num_nodes, dimensions, sparse=True).to(device)
    optimizer = torch.optim.SparseAdam(emb_table.parameters(), lr=lr)

    batch_size = 2048
    neg_samples = 3
    emb_table.train()
    for epoch in range(1, epochs + 1):
        perm = torch.randperm(pairs.size(0), device=device)
        total_loss = 0.0
        num_batches = 0
        for start_idx in range(0, pairs.size(0), batch_size):
            batch_idx = perm[start_idx:start_idx + batch_size]
            batch = pairs[batch_idx]  # [B, 2]
            B = batch.size(0)

            neg = torch.randint(0, num_nodes, (B, neg_samples), device=device)  # [B, neg_samples]

            optimizer.zero_grad()
            u = emb_table(batch[:, 0])       # [B, dim]
            v_pos = emb_table(batch[:, 1])   # [B, dim]
            v_neg = emb_table(neg)           # [B, neg_samples, dim]

            score_pos = (u * v_pos).sum(dim=1)                          # [B]
            score_neg = torch.bmm(v_neg, u.unsqueeze(2)).squeeze(2)     # [B, neg_samples]

            loss = -torch.log(torch.sigmoid(score_pos) + 1e-8).mean() \
                   - torch.log(1 - torch.sigmoid(score_neg) + 1e-8).mean()

            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            num_batches += 1

        print(f"  Epoch {epoch}/{epochs} — avg loss: {total_loss / max(num_batches,1):.4f}")
    
    emb_table.eval()
    with torch.no_grad():
        embeddings = emb_table(torch.arange(num_nodes, device=device))
    return embeddings.cpu()


async def store_embeddings_in_neo4j(embeddings, idx_to_node, org_id: str, engagement_id: str, dimensions=128):
    """Store the learned embeddings back to Neo4j as node properties, scoped to tenant+engagement."""
    print(f"Storing embeddings in Neo4j for org={org_id}, engagement={engagement_id}...")
    
    batch = []
    for idx in range(embeddings.size(0)):
        objectid = idx_to_node[idx]
        embedding = embeddings[idx].tolist()
        batch.append({
            "objectid": objectid,
            "embedding": embedding
        })
    
    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        batch_size = 500
        updated = 0
        
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            
            query = """
            UNWIND $batch AS item
            MATCH (n)
            WHERE
                (n.objectid = item.objectid
                 OR n.actor_id = item.objectid
                 OR n.technique_id = item.objectid
                 OR n.name = item.objectid)
                AND n.org_id = $org_id
                AND n.engagement_id = $engagement_id
            SET n.embedding = item.embedding,
                n.embedding_dim = $dimensions
            """
            
            await ts.run(query, batch=chunk, dimensions=dimensions)
            updated += len(chunk)
            print(f"  Updated {updated}/{len(batch)} nodes...")
        
        print(f"  All {updated} embeddings stored")


async def run_embeddings(org_id: str, engagement_id: str):
    print("=" * 60)
    print("GNN Embeddings Generation — Pure-PyTorch Node2Vec (no pyg-lib)")
    print(f"  org_id: {org_id}")
    print(f"  engagement_id: {engagement_id}")
    print("=" * 60)
    
    # 1. Fetch graph from Neo4j (tenant-scoped)
    G, node_to_idx, idx_to_node = await fetch_graph_from_neo4j(org_id, engagement_id)
    
    if G.number_of_nodes() == 0:
        print("ERROR: No nodes found in graph. Run ETL first.")
        return
    
    # 2. Build PyG Data
    data = build_pyg_data(G, node_to_idx)
    
    # 3. Run Node2Vec
    embeddings = run_node2vec(data)
    
    # 4. Store embeddings back to Neo4j (tenant-scoped)
    await store_embeddings_in_neo4j(embeddings, idx_to_node, org_id, engagement_id)
    
    print("\n" + "=" * 60)
    print("Embeddings generation complete!")
    print("=" * 60)
    
    # Quick verification
    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        result = await ts.run("""
            MATCH (n) 
            WHERE n.embedding IS NOT NULL 
              AND n.org_id = $org_id 
              AND n.engagement_id = $engagement_id
            RETURN count(n) AS count, size(n.embedding) AS dim
        """, org_id=org_id, engagement_id=engagement_id)
        record = await result.single()
        print(f"Verification: {record['count']} nodes have {record['dim']}-dim embeddings")


def main():
    parser = argparse.ArgumentParser(description="Generate Node2Vec embeddings for tenant-scoped graph")
    parser.add_argument("--org_id", required=True, help="Organization ID (tenant)")
    parser.add_argument("--engagement_id", required=True, help="Engagement ID")
    args = parser.parse_args()
    
    asyncio.run(run_embeddings(args.org_id, args.engagement_id))


if __name__ == "__main__":
    main()