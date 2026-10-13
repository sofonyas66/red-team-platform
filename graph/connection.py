"""
graph/connection.py — Async Neo4j driver (singleton).

All code that opens Neo4j sessions must import `driver` from here.
Direct driver construction elsewhere is not allowed (enforced by
scripts/check_tenant_isolation.sh).
"""
import os
from neo4j import AsyncGraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")

def get_driver():
    """Get or create the Neo4j driver, ensuring it's in the same event loop."""
    if not hasattr(get_driver, "_driver"):
        driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_lifetime=30 * 60,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60,
        )
        get_driver._driver = driver
    return get_driver._driver


async def verify_connection() -> bool:
    """Verify Neo4j connectivity (async)."""
    try:
        await driver.verify_connectivity()
        return True
    except Exception:
        return False


async def close_driver():
    """Close the driver connection pool (call on app shutdown)."""
    await driver.close()


if __name__ == "__main__":
    import asyncio

    async def _main():
        if await verify_connection():
            print("✓ Neo4j connection successful")
            async with driver.session() as session:
                result = await session.run("RETURN 'Connection successful' AS msg")
                record = await result.single()
                if record:
                    print(record["msg"])
        else:
            print("✗ Neo4j connection failed")
            raise SystemExit(1)
        await close_driver()

    asyncio.run(_main())