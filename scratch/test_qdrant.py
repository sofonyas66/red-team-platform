from qdrant_client import QdrantClient

qdrant = QdrantClient(host="localhost", port=6333)

try:
    cols = qdrant.get_collections().collections
    print("Qdrant Collections:")
    for c in cols:
        print(f"  Collection Name: {c.name}")
        info = qdrant.get_collection(collection_name=c.name)
        print(f"    Points Count: {info.points_count}")
        print(f"    Status: {info.status}")
except Exception as e:
    print(f"Error: {e}")
