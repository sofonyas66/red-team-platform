from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

driver = GraphDatabase.driver(URI, auth=AUTH)

with driver.session() as session:
    result = session.run("RETURN 'Connection successful' AS msg")
    print(result.single()["msg"])

driver.close()
