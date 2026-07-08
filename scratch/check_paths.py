from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

driver = GraphDatabase.driver(URI, auth=AUTH)
with driver.session() as session:
    # 1. Print some Users and Computers
    print("Users:")
    res = session.run("MATCH (u:User) RETURN u.name as name, u.objectid as objectid LIMIT 5")
    for r in res:
        print(f"  {r['name']} ({r['objectid']})")
    
    print("\nComputers:")
    res = session.run("MATCH (c:Computer) RETURN c.name as name, c.objectid as objectid LIMIT 5")
    for r in res:
        print(f"  {r['name']} ({r['objectid']})")
        
    # 2. Check if a path exists from ANY User to ANY Computer (directed, 1-5 hops)
    print("\nDirected path check (1-5 hops):")
    res = session.run("""
        MATCH p = (u:User)-[*1..5]->(c:Computer)
        RETURN u.name as src, c.name as dst, length(p) as hops, [r in relationships(p) | type(r)] as rels
        LIMIT 5
    """)
    records = list(res)
    if records:
        for r in records:
            print(f"  Path: {r['src']} -> {r['rels']} -> {r['dst']} ({r['hops']} hops)")
    else:
        print("  No directed paths found from any User to any Computer within 5 hops.")
        
    # 3. Check if an undirected path exists (1-5 hops)
    print("\nUndirected path check (1-5 hops):")
    res = session.run("""
        MATCH p = (u:User)-[*1..5]-(c:Computer)
        RETURN u.name as src, c.name as dst, length(p) as hops
        LIMIT 5
    """)
    records = list(res)
    if records:
        for r in records:
            print(f"  Undirected path exists: {r['src']} - {r['dst']} ({r['hops']} hops)")
    else:
        print("  No undirected paths found either.")

    # 4. Check reversed path check: Computer -> User
    print("\nReversed path check (1-5 hops Computer -> User):")
    res = session.run("""
        MATCH p = (c:Computer)-[*1..5]->(u:User)
        RETURN c.name as src, u.name as dst, length(p) as hops, [r in relationships(p) | type(r)] as rels
        LIMIT 5
    """)
    records = list(res)
    if records:
        for r in records:
            print(f"  Reversed path: {r['src']} -> {r['rels']} -> {r['dst']} ({r['hops']} hops)")
    else:
        print("  No reversed paths found.")

    # 5. Let's look at relationships of Computers
    print("\nRelationships connected to Computers:")
    res = session.run("""
        MATCH (c:Computer)-[r]-(n)
        RETURN labels(c)[0] as c_label, c.name as c_name, type(r) as r_type, startNode(r) = c as c_is_start, labels(n)[0] as n_label, n.name as n_name
        LIMIT 10
    """)
    for r in res:
        direction = f"{r['c_name']} -[:{r['r_type']}]-> {r['n_name']}" if r['c_is_start'] else f"{r['n_name']} -[:{r['r_type']}]-> {r['c_name']}"
        print(f"  {direction}  ({r['n_label']})")
        
driver.close()
