from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

driver = GraphDatabase.driver(URI, auth=AUTH)
with driver.session() as session:
    res = session.run("MATCH ()-[r]->() LIMIT 5 RETURN type(r) as type, properties(r) as props")
    for r in res:
        print(f"Rel Type: {r['type']}, Properties: {r['props']}")
driver.close()
