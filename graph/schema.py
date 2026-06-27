from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

SCHEMA = [
    # ── Constraints (unique IDs per node type) ────────────────────────────
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.objectid IS UNIQUE",
    "CREATE CONSTRAINT computer_id IF NOT EXISTS FOR (c:Computer) REQUIRE c.objectid IS UNIQUE",
    "CREATE CONSTRAINT group_id IF NOT EXISTS FOR (g:Group) REQUIRE g.objectid IS UNIQUE",
    "CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (d:Domain) REQUIRE d.objectid IS UNIQUE",
    "CREATE CONSTRAINT gpo_id IF NOT EXISTS FOR (g:GPO) REQUIRE g.objectid IS UNIQUE",
    "CREATE CONSTRAINT ou_id IF NOT EXISTS FOR (o:OU) REQUIRE o.objectid IS UNIQUE",
    "CREATE CONSTRAINT actor_id IF NOT EXISTS FOR (a:ThreatActor) REQUIRE a.actor_id IS UNIQUE",
    "CREATE CONSTRAINT technique_id IF NOT EXISTS FOR (t:Technique) REQUIRE t.technique_id IS UNIQUE",
    "CREATE CONSTRAINT sector_id IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE",

    # ── Indexes (fast lookups) ─────────────────────────────────────────────
    "CREATE INDEX user_name IF NOT EXISTS FOR (u:User) ON (u.name)",
    "CREATE INDEX computer_name IF NOT EXISTS FOR (c:Computer) ON (c.name)",
    "CREATE INDEX group_name IF NOT EXISTS FOR (g:Group) ON (g.name)",
    "CREATE INDEX technique_name IF NOT EXISTS FOR (t:Technique) ON (t.name)",
]

def create_schema():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        for stmt in SCHEMA:
            session.run(stmt)
            print(f"OK: {stmt[:60]}...")
    driver.close()
    print("\nSchema ready.")

if __name__ == "__main__":
    create_schema()
