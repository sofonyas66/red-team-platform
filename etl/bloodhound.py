import json
import sys
import argparse
from graph.connection import driver

def ingest_data(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    # 1. Ingest Nodes
    node_map = {
        'User': 'users',
        'Computer': 'computers',
        'Group': 'groups',
        'Domain': 'domains'
    }

    with driver.session() as session:
        for label, key in node_map.items():
            nodes = data.get(key, [])
            if not nodes:
                continue
            
            print(f"Ingesting {key}...", end=" ", flush=True)
            
            # Using UNWIND for batch processing
            query = f"""
            UNWIND $batch AS node
            MERGE (n:{label} {{objectid: node.objectid}})
            SET n.name = node.name,
                n.enabled = coalesce(node.enabled, true),
                n.admincount = coalesce(node.admincount, false),
                n.operatingsystem = coalesce(node.operatingsystem, 'Unknown'),
                n.source = 'bloodhound'
            """
            session.run(query, batch=nodes)
            print(f"done ({len(nodes)})")

        # 2. Ingest Relationships
        rels = data.get('relationships', [])
        if rels:
            print(f"Ingesting relationships...", end=" ", flush=True)
            # Find the label of source/target dynamically is hard in one go, 
            # so we assume we query for the nodes by objectid (which is unique)
            query = """
            UNWIND $batch AS rel
            MATCH (s {objectid: rel.source})
            MATCH (t {objectid: rel.target})
            CALL {
                WITH s, t, rel
                // We use apoc if allowed, but here pure cypher merge per type
                // Since pure cypher doesn't allow dynamic rel types, we use this structure:
                FOREACH (_ IN CASE WHEN rel.type = 'MemberOf' THEN [1] ELSE [] END | MERGE (s)-[r:MemberOf]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'AdminTo' THEN [1] ELSE [] END | MERGE (s)-[r:AdminTo]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'HasSession' THEN [1] ELSE [] END | MERGE (s)-[r:HasSession]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'GenericAll' THEN [1] ELSE [] END | MERGE (s)-[r:GenericAll]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'GenericWrite' THEN [1] ELSE [] END | MERGE (s)-[r:GenericWrite]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'WriteDacl' THEN [1] ELSE [] END | MERGE (s)-[r:WriteDacl]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'Contains' THEN [1] ELSE [] END | MERGE (s)-[r:Contains]->(t) SET r.source = 'bloodhound')
                FOREACH (_ IN CASE WHEN rel.type = 'GpLink' THEN [1] ELSE [] END | MERGE (s)-[r:GpLink]->(t) SET r.source = 'bloodhound')
            }
            """
            session.run(query, batch=rels)
            print(f"done ({len(rels)})")

    print("\nIngestion complete.")
    # Final Summary
    with driver.session() as session:
        summary = session.run("MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count").data()
        print("Final Node Counts:", summary)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", help="Path to BloodHound JSON file")
    args = parser.parse_args()
    ingest_data(args.file_path)
