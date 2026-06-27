import json
import os
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "changeme")

ACTORS_DIR = os.path.join(os.path.dirname(__file__), "actors")


def load_bundle(session, bundle: dict):
    objects = bundle.get("objects", [])

    # Index by ID for relationship resolution
    by_id = {obj["id"]: obj for obj in objects}

    for obj in objects:
        t = obj["type"]

        if t == "threat-actor":
            session.run("""
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

            # Link actor to targeted sectors
            for sector in obj.get("sectors", []):
                session.run("""
                    MERGE (s:Sector {name: $sector})
                    WITH s
                    MATCH (a:ThreatActor {actor_id: $actor_id})
                    MERGE (a)-[:TARGETS]->(s)
                """, {"sector": sector, "actor_id": obj["id"]})

        elif t == "attack-pattern":
            session.run("""
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
                session.run("""
                    MATCH (a:ThreatActor {actor_id: $actor_id})
                    MATCH (t:Technique {technique_id: $tid})
                    MERGE (a)-[:USES]->(t)
                """, {
                    "actor_id": src["id"],
                    "tid": tgt.get("technique_id", tgt["id"]),
                })


def load_all():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    with driver.session() as session:
        for fname in os.listdir(ACTORS_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(ACTORS_DIR, fname)
            with open(fpath) as f:
                bundle = json.load(f)
            print(f"Loading {fname}...")
            load_bundle(session, bundle)
            print(f"  Done.")
    driver.close()
    print("\nETI-Core loaded.")


if __name__ == "__main__":
    load_all()
