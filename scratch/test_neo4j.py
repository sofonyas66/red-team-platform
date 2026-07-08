from neo4j import GraphDatabase
import sys

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

print("Connecting to Neo4j...")
try:
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        print("Running nodes query...")
        res = session.run("MATCH (n) RETURN labels(n)[0] as lbl, count(n) as cnt")
        for r in res:
            print(f"Node: {r['lbl']} = {r['cnt']}")
        
        print("Running rels query...")
        res = session.run("MATCH ()-[r]->() RETURN type(r) as t, count(r) as cnt")
        for r in res:
            print(f"Rel: {r['t']} = {r['cnt']}")
    driver.close()
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
