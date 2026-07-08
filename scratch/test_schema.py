from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

driver = GraphDatabase.driver(URI, auth=AUTH)
with driver.session() as session:
    print("Constraints:")
    res = session.run("SHOW CONSTRAINTS")
    for r in res:
        print(f"  Name: {r.get('name')}, Type: {r.get('type')}, EntityType: {r.get('entityType')}, Labels: {r.get('labelsOrTypes')}, Props: {r.get('properties')}")
    
    print("\nIndexes:")
    res = session.run("SHOW INDEXES")
    for r in res:
        print(f"  Name: {r.get('name')}, State: {r.get('state')}, Type: {r.get('type')}, EntityType: {r.get('entityType')}, Labels: {r.get('labelsOrTypes')}, Props: {r.get('properties')}")

    print("\nNone labels details:")
    res = session.run("MATCH (n) WHERE labels(n) = [] RETURN id(n) as id, n.name as name, n.objectid as objectid, properties(n) as props")
    for r in res:
        print(f"  ID: {r['id']}, Name: {r['name']}, ObjectId: {r['objectid']}, Props: {r['props']}")
driver.close()
