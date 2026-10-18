"""
graph/schema.py — Neo4j schema bootstrap (constraints + indexes).

This is NOT tenant-scoped: it runs once at startup against the whole
database to ensure structural constraints exist.  Uses the shared async
driver directly (not TenantSession).
"""
import asyncio
from graph.connection import get_driver

SCHEMA = [
    # ── Constraints (unique IDs per node type) ────────────────────────────
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.objectid IS UNIQUE",
    "CREATE CONSTRAINT computer_id IF NOT EXISTS FOR (c:Computer) REQUIRE c.objectid IS UNIQUE",
    "CREATE CONSTRAINT group_id IF NOT EXISTS FOR (g:Group) REQUIRE g.objectid IS UNIQUE",
    "CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (d:Domain) REQUIRE d.objectid IS UNIQUE",
    "CREATE CONSTRAINT gpo_id IF NOT EXISTS FOR (g:GPO) REQUIRE g.objectid IS UNIQUE",
    "CREATE CONSTRAINT ou_id IF NOT EXISTS FOR (o:OU) REQUIRE o.objectid IS UNIQUE",
    "CREATE CONSTRAINT container_id IF NOT EXISTS FOR (c:Container) REQUIRE c.objectid IS UNIQUE",
    "CREATE CONSTRAINT actor_id IF NOT EXISTS FOR (a:ThreatActor) REQUIRE a.actor_id IS UNIQUE",
    "CREATE CONSTRAINT technique_id IF NOT EXISTS FOR (t:Technique) REQUIRE t.technique_id IS UNIQUE",
    "CREATE CONSTRAINT sector_id IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE",

    # ── Indexes (fast lookups) ─────────────────────────────────────────────
    "CREATE INDEX user_name IF NOT EXISTS FOR (u:User) ON (u.name)",
    "CREATE INDEX computer_name IF NOT EXISTS FOR (c:Computer) ON (c.name)",
    "CREATE INDEX group_name IF NOT EXISTS FOR (g:Group) ON (g.name)",
    "CREATE INDEX container_name IF NOT EXISTS FOR (c:Container) ON (c.name)",
    "CREATE INDEX technique_name IF NOT EXISTS FOR (t:Technique) ON (t.name)",
]


async def create_schema():
    """Create constraints and indexes.  Safe to call at every startup (IF NOT EXISTS)."""
    driver = get_driver()
    async with driver.session() as session:
        for stmt in SCHEMA:
            await session.run(stmt)
            print(f"OK: {stmt[:60]}...")
    print("\nSchema ready.")


if __name__ == "__main__":
    asyncio.run(create_schema())
