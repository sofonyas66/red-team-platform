from neo4j import GraphDatabase

URI = "bolt://127.0.0.1:7687"
AUTH = ("neo4j", "changeme")

# driver = GraphDatabase.driver(URI, auth=AUTH)
#
# with driver.session() as session:
#     result = session.run("RETURN 'Connection successful' AS msg")
#     print(result.single()["msg"])
#
# driver.close()

driver = GraphDatabase.driver(URI, auth=AUTH)
