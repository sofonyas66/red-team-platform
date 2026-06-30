"""
llm/rag.py — Retrieval-Augmented Generation for threat intelligence context

Embeds ETI-Core threat actor profiles and ATT&CK technique descriptions
from Neo4j into Qdrant vector store. Retrieves relevant chunks for queries.
"""

from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from graph.connection import driver

# Initialize Qdrant and SentenceTransformer
qdrant = QdrantClient(host="localhost", port=6333, timeout=120.0)
encoder = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim, fast, local

COLLECTION_NAME = "eti_core"
VECTOR_SIZE = 384


def init_collection():
    """Create Qdrant collection if it doesn't exist."""
    collections = qdrant.get_collections().collections
    if COLLECTION_NAME not in [c.name for c in collections]:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE
            )
        )
        print(f"Created Qdrant collection: {COLLECTION_NAME}")
    else:
        print(f"Qdrant collection '{COLLECTION_NAME}' already exists")


def embed_eti_core():
    """
    Pull every ThreatActor and Technique node from Neo4j with their descriptions.
    For each, create a text chunk combining name + description + tactic + sectors.
    Embed with sentence-transformers and store in Qdrant collection "eti_core".
    """
    print("Initializing Qdrant collection...")
    init_collection()

    chunks = []

    print("Fetching ThreatActor and Technique nodes from Neo4j...")
    with driver.session() as session:
        # 1. Fetch ThreatActors
        actor_result = session.run("""
            MATCH (a:ThreatActor)
            OPTIONAL MATCH (a)-[:TARGETS]->(s:Sector)
            RETURN a.actor_id AS id,
                   a.name AS name,
                   a.description AS description,
                   a.sophistication AS sophistication,
                   a.motivation AS motivation,
                   a.resource_level AS resource_level,
                   collect(s.name) AS sectors
        """)
        for record in actor_result:
            sectors = record["sectors"]
            sectors_str = ", ".join(sectors) if sectors else "None"
            text = (
                f"Threat Actor: {record['name']}\n"
                f"Description: {record['description'] or 'No description'}\n"
                f"Sophistication: {record['sophistication'] or 'Unknown'}\n"
                f"Motivation: {record['motivation'] or 'Unknown'}\n"
                f"Resource Level: {record['resource_level'] or 'Unknown'}\n"
                f"Targeted Sectors: {sectors_str}"
            )
            chunks.append({
                "id": record["id"],
                "type": "threat_actor",
                "name": record["name"],
                "text": text,
                "properties": {
                    "actor_id": record["id"],
                    "name": record["name"],
                    "description": record["description"],
                    "sophistication": record["sophistication"],
                    "motivation": record["motivation"],
                    "resource_level": record["resource_level"],
                    "sectors": sectors
                }
            })

        # 2. Fetch Techniques
        tech_result = session.run("""
            MATCH (t:Technique)
            RETURN t.technique_id AS id,
                   t.name AS name,
                   t.description AS description,
                   t.tactic AS tactic
        """)
        for record in tech_result:
            text = (
                f"Technique: {record['name']} (ID: {record['id']})\n"
                f"Tactic: {record['tactic'] or 'Unknown'}\n"
                f"Description: {record['description'] or 'No description'}"
            )
            chunks.append({
                "id": record["id"],
                "type": "technique",
                "name": record["name"],
                "text": text,
                "properties": {
                    "technique_id": record["id"],
                    "name": record["name"],
                    "description": record["description"],
                    "tactic": record["tactic"]
                }
            })

    if not chunks:
        print("No nodes found in Neo4j. Ingest ETI-Core data first.")
        return

    print(f"Embedding {len(chunks)} chunks using all-MiniLM-L6-v2...")
    texts = [c["text"] for c in chunks]
    embeddings = encoder.encode(texts, show_progress_bar=True, batch_size=32)

    points = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        points.append(models.PointStruct(
            id=i,
            vector=emb.tolist(),
            payload={
                "id": chunk["id"],
                "type": chunk["type"],
                "name": chunk["name"],
                "text": chunk["text"],
                "properties": chunk["properties"]
            }
        ))

    print(f"Storing embedded points into Qdrant collection '{COLLECTION_NAME}'...")
    # Batch upsert
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i+batch_size]
        qdrant.upsert(collection_name=COLLECTION_NAME, points=batch)

    print(f"Successfully stored {len(points)} chunks in Qdrant.")


def retrieve_context(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Embed the query text, search Qdrant collection "eti_core",
    return top_k most relevant chunks with their payloads.
    """
    query_vector = encoder.encode([query])[0].tolist()
    
    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True
    ).points

    output = []
    for hit in results:
        payload = hit.payload
        output.append({
            "id": payload["id"],
            "type": payload["type"],
            "name": payload["name"],
            "text": payload["text"],
            "score": hit.score,
            "properties": payload.get("properties", {})
        })
    return output


if __name__ == "__main__":
    embed_eti_core()
    print("\nTesting retrieval with 'government sector spearphishing':")
    results = retrieve_context("government sector spearphishing")
    for r in results:
        print(f"\n[{r['type'].upper()}] {r['name']} (Score: {r['score']:.4f})")
        print(r['text'])