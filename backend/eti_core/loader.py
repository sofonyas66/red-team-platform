"""
eti_core/loader.py — Load STIX2 threat-actor bundles into Neo4j.

ETI-Core data (threat actors, techniques) is NOT tenant-scoped — it is
shared reference data for all tenants.  Uses the async driver directly
(not TenantSession).
"""
import asyncio
import json
import os
from graph.connection import get_driver

ACTORS_DIR = os.path.join(os.path.dirname(__file__), "actors")


async def load_bundle(session, bundle: dict):
    """Load a single STIX2 bundle into Neo4j via the given async session."""
    objects = bundle.get("objects", [])
    by_id = {obj["id"]: obj for obj in objects}

    for obj in objects:
        t = obj["type"]

        if t == "threat-actor":
            await session.run("""
                MERGE (a:ThreatActor {actor_id: $id})
                SET a.name = $name,
                    a.description = $description,
                    a.sophistication = $sophistication,
                    a.motivation = $motivation,
                    a.resource_level = $resource_level
            """, {
                "id": obj["id"],
                "name": obj["name"],
                "description": obj.get("description", ""),
                "sophistication": obj.get("sophistication", "unknown"),
                "motivation": obj.get("primary_motivation", "unknown"),
                "resource_level": obj.get("resource_level", "unknown"),
            })

            for sector in obj.get("sectors", []):
                await session.run("""
                    MERGE (s:Sector {name: $sector})
                    WITH s
                    MATCH (a:ThreatActor {actor_id: $actor_id})
                    MERGE (a)-[:TARGETS]->(s)
                """, {"sector": sector, "actor_id": obj["id"]})

        elif t == "attack-pattern":
            await session.run("""
                MERGE (t:Technique {technique_id: $tid})
                SET t.name = $name,
                    t.tactic = $tactic,
                    t.description = $description
            """, {
                "tid": obj.get("technique_id", obj["id"]),
                "name": obj["name"],
                "tactic": obj.get("tactic", "unknown"),
                "description": obj.get("description", ""),
            })

        elif t == "relationship" and obj["relationship_type"] == "uses":
            src = by_id.get(obj["source_ref"], {})
            tgt = by_id.get(obj["target_ref"], {})
            if src.get("type") == "threat-actor" and tgt.get("type") == "attack-pattern":
                await session.run("""
                    MATCH (a:ThreatActor {actor_id: $actor_id})
                    MATCH (t:Technique {technique_id: $tid})
                    MERGE (a)-[:USES]->(t)
                """, {
                    "actor_id": src["id"],
                    "tid": tgt.get("technique_id", tgt["id"]),
                })


async def load_all():
    """Load all STIX2 bundles from the actors directory into Neo4j."""
    driver = get_driver()
    async with driver.session() as session:
        for fname in os.listdir(ACTORS_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(ACTORS_DIR, fname)
            with open(fpath) as f:
                bundle = json.load(f)
            print(f"Loading {fname}...")
            await load_bundle(session, bundle)
            print("  Done.")
    print("\nETI-Core loaded.")


if __name__ == "__main__":
    asyncio.run(load_all())
