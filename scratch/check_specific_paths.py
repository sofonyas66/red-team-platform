from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

driver = GraphDatabase.driver(URI, auth=AUTH)
with driver.session() as session:
    print("Shortest path from HODOR to any Computer:")
    res = session.run("""
        MATCH p = shortestPath((u:User {name: "HODOR@NORTH.SEVENKINGDOMS.LOCAL"})-[*1..10]->(c:Computer))
        RETURN c.name as comp, length(p) as hops, [r in relationships(p) | type(r)] as rels
    """)
    records = list(res)
    if records:
        for r in records:
            print(f"  To {r['comp']}: {r['hops']} hops via {r['rels']}")
    else:
        print("  No path found from HODOR to any Computer!")

    print("\nShortest path from ROBB to any Computer:")
    res = session.run("""
        MATCH p = shortestPath((u:User {name: "ROBB.STARK@NORTH.SEVENKINGDOMS.LOCAL"})-[*1..10]->(c:Computer))
        RETURN c.name as comp, length(p) as hops, [r in relationships(p) | type(r)] as rels
    """)
    records = list(res)
    if records:
        for r in records:
            print(f"  To {r['comp']}: {r['hops']} hops via {r['rels']}")
    else:
        print("  No path found from ROBB to any Computer!")

    print("\nAll User paths to WINTERFELL:")
    res = session.run("""
        MATCH p = (u:User)-[*1..3]->(c:Computer {name: "WINTERFELL.NORTH.SEVENKINGDOMS.LOCAL"})
        RETURN u.name as user, length(p) as hops, [r in relationships(p) | type(r)] as rels
        LIMIT 5
    """)
    for r in res:
        print(f"  From {r['user']}: {r['hops']} hops via {r['rels']}")
driver.close()
