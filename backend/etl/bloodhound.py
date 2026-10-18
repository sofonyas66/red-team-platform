"""
BloodHound CE (SharpHound v6) → Neo4j ingestion.

Input:  A folder of per-type JSON files produced by SharpHound.
Output: MERGE-based Neo4j nodes + relationships (idempotent).

Usage:
    python -m etl.bloodhound /path/to/north_extracted
"""

import json
import glob
import os
import sys
import logging
from collections import defaultdict
from graph.tenant_session import TenantSession



logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── ACL RightName values we create relationship types for ────────────────
HANDLED_ACE_RIGHTS = frozenset([
    "GenericAll", "GenericWrite", "WriteDacl", "WriteOwner",
    "Owns", "AllExtendedRights", "ForceChangePassword", "AddMember",
])

# ── ADCS / PKI types to skip for now ────────────────────────────────────
ADCS_TYPES = frozenset(["rootcas", "aiacas", "enterprisecas", "ntauthstores", "certtemplates"])

# Processing order — objects first, then relationships in a second pass
OBJECT_TYPES_ORDER = ["domains", "containers", "ous", "gpos", "groups", "computers", "users"]


# ═══════════════════════════════════════════════════════════════════════════
#  File loading
# ═══════════════════════════════════════════════════════════════════════════

def _load_folder(folder_path: str) -> dict:
    """Load all JSON files from a SharpHound export folder.

    Returns: {meta_type: [records...], ...}
    """
    files = glob.glob(os.path.join(folder_path, "*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON files found in {folder_path}")

    loaded = {}
    for fpath in sorted(files):
        with open(fpath) as f:
            raw = json.load(f)
        meta = raw.get("meta", {})
        meta_type = meta.get("type", "unknown")
        data = raw.get("data", [])

        if meta_type in ADCS_TYPES:
            log.info("Skipping ADCS/PKI type '%s' (%d records) — future phase", meta_type, len(data))
            continue

        if meta_type not in OBJECT_TYPES_ORDER:
            log.warning("Unknown meta.type '%s' in %s — skipping", meta_type, os.path.basename(fpath))
            continue

        loaded[meta_type] = data
        log.info("Loaded %-12s  %4d records  from %s", meta_type, len(data), os.path.basename(fpath))

    return loaded


# ═══════════════════════════════════════════════════════════════════════════
#  Node ingestion (Pass 1)
# ═══════════════════════════════════════════════════════════════════════════

# Each entry:  (label, [property keys to pull from Properties])
NODE_CONFIG = {
    "users":      ("User",      ["name", "samaccountname", "enabled", "admincount", "description"]),
    "computers":  ("Computer",  ["name", "samaccountname", "operatingsystem"]),
    "groups":     ("Group",     ["name", "admincount"]),
    "domains":    ("Domain",    ["name", "domainsid", "functionallevel"]),
    "gpos":       ("GPO",       ["name"]),
    "ous":        ("OU",        ["name"]),
    "containers": ("Container", ["name"]),
}


async def _ingest_nodes(session, meta_type: str, records: list, org_id: str, engagement_id: str) -> int:
    """MERGE nodes for one object type. Returns count ingested."""
    label, prop_keys = NODE_CONFIG[meta_type]

    # Build dynamic SET clause from the prop_keys list
    set_parts = [f"n.{k} = row.props.{k}" for k in prop_keys]
    set_parts.append("n.source = 'bloodhound'")
    set_clause = ", ".join(set_parts)

    # Build the batch — flatten Properties into a props dict for Cypher
    batch = []
    for rec in records:
        oid = rec.get("ObjectIdentifier")
        if not oid:
            continue
        props = {}
        raw_props = rec.get("Properties") or {}
        for k in prop_keys:
            props[k] = raw_props.get(k)
        batch.append({"objectid": oid, "props": props})

    if not batch:
        return 0

    # org_id + engagement_id are part of the MERGE key to prevent cross-tenant
    # node collisions when objectids/SIDs overlap across customer datasets.
    query = f"""
    UNWIND $batch AS row
    MERGE (n:{label} {{objectid: row.objectid, org_id: $org_id, engagement_id: $engagement_id}})
    SET {set_clause}
    """
    await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
    log.info("  %-10s  %4d nodes merged", label, len(batch))
    return len(batch)


# ═══════════════════════════════════════════════════════════════════════════
#  Relationship ingestion (Pass 2)
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_stub(session, objectid: str):
    """MERGE a minimal stub node with just objectid if it doesn't exist yet.
    Uses label-less merge so it doesn't conflict with typed constraints."""
    # We can't MERGE without a label reliably with uniqueness constraints,
    # but we can MERGE with each possible label — instead, we'll handle
    # stubs inline in the batch queries by using MERGE on {objectid} with
    # appropriate labels.  This function is kept as a fallback.
    pass


async def _ingest_memberof(session, records: list, org_id: str, engagement_id: str) -> int:
    """MemberOf from each Group's Members array."""
    batch = []
    for rec in records:
        group_oid = rec.get("ObjectIdentifier")
        if not group_oid:
            continue
        for member in (rec.get("Members") or []):
            member_oid = member.get("ObjectIdentifier")
            if member_oid:
                batch.append({"member": member_oid, "group": group_oid})

    if not batch:
        return 0

    query = """
    UNWIND $batch AS row
    MERGE (m {objectid: row.member, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET m.source = 'bloodhound'
    WITH m, row
    MERGE (g {objectid: row.group, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET g.source = 'bloodhound'
    MERGE (m)-[:MemberOf]->(g)
    """
    await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
    return len(batch)


async def _ingest_aces(session, all_records: dict, org_id: str, engagement_id: str) -> tuple:
    """ACL relationships from every object type's Aces array.

    Returns: (dict of {RightName: count}, set of skipped RightName values)
    """
    # Group ACEs by RightName for batch processing
    ace_batches = defaultdict(list)
    skipped_rights = set()

    for meta_type in OBJECT_TYPES_ORDER:
        for rec in all_records.get(meta_type, []):
            obj_oid = rec.get("ObjectIdentifier")
            if not obj_oid:
                continue
            for ace in (rec.get("Aces") or []):
                right_name = ace.get("RightName")
                principal_sid = ace.get("PrincipalSID")
                if not right_name or not principal_sid:
                    continue
                if right_name in HANDLED_ACE_RIGHTS:
                    ace_batches[right_name].append({
                        "principal": principal_sid,
                        "target": obj_oid,
                    })
                else:
                    skipped_rights.add(right_name)

    counts = {}
    for right_name, batch in ace_batches.items():
        if not batch:
            continue
        query = f"""
        UNWIND $batch AS row
        MERGE (p {{objectid: row.principal, org_id: $org_id, engagement_id: $engagement_id}})
        ON CREATE SET p.source = 'bloodhound'
        WITH p, row
        MERGE (t {{objectid: row.target, org_id: $org_id, engagement_id: $engagement_id}})
        ON CREATE SET t.source = 'bloodhound'
        MERGE (p)-[:{right_name}]->(t)
        """
        await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
        counts[right_name] = len(batch)
        log.info("  %-22s  %4d ACL edges", right_name, len(batch))

    return counts, skipped_rights


async def _ingest_contains(session, all_records: dict, org_id: str, engagement_id: str) -> int:
    """Contains relationships from every object's ContainedBy field."""
    batch = []
    for meta_type in OBJECT_TYPES_ORDER:
        for rec in all_records.get(meta_type, []):
            obj_oid = rec.get("ObjectIdentifier")
            contained_by = rec.get("ContainedBy")
            if not obj_oid or not contained_by:
                continue
            parent_oid = contained_by.get("ObjectIdentifier")
            if parent_oid:
                batch.append({"parent": parent_oid, "child": obj_oid})

    if not batch:
        return 0

    query = """
    UNWIND $batch AS row
    MERGE (p {objectid: row.parent, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET p.source = 'bloodhound'
    WITH p, row
    MERGE (c {objectid: row.child, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET c.source = 'bloodhound'
    MERGE (p)-[:Contains]->(c)
    """
    await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
    return len(batch)


async def _ingest_hassession(session, records: list, org_id: str, engagement_id: str) -> tuple:
    """HasSession from Computer's Sessions field.

    Returns: (count of HasSession edges, count of computers with uncollected sessions)
    """
    batch = []
    uncollected = 0

    for rec in records:
        comp_oid = rec.get("ObjectIdentifier")
        if not comp_oid:
            continue
        sessions = rec.get("Sessions") or {}
        if not sessions.get("Collected", False):
            uncollected += 1
            continue
        for result in (sessions.get("Results") or []):
            user_oid = result.get("ObjectIdentifier")
            if user_oid:
                batch.append({"computer": comp_oid, "user": user_oid})

    if not batch:
        return 0, uncollected

    query = """
    UNWIND $batch AS row
    MERGE (c {objectid: row.computer, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET c.source = 'bloodhound'
    WITH c, row
    MERGE (u {objectid: row.user, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET u.source = 'bloodhound'
    MERGE (c)-[:HasSession]->(u)
    """
    await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
    return len(batch), uncollected


async def _ingest_adminto(session, records: list, org_id: str, engagement_id: str) -> tuple:
    """AdminTo from Computer's LocalGroups array.

    Finds the built-in Administrators group by SID suffix -544.

    Returns: (count of AdminTo edges, count of computers with uncollected localgroups)
    """
    batch = []
    uncollected = 0

    for rec in records:
        comp_oid = rec.get("ObjectIdentifier")
        if not comp_oid:
            continue
        local_groups = rec.get("LocalGroups") or []
        if not local_groups:
            # No LocalGroups data at all — count as uncollected
            uncollected += 1
            continue

        found_admin_group = False
        for lg in local_groups:
            lg_sid = lg.get("ObjectIdentifier", "")
            # Well-known RID for built-in Administrators is -544
            if not lg_sid.endswith("-544"):
                continue
            found_admin_group = True
            if not lg.get("Collected", False):
                uncollected += 1
                break
            for result in (lg.get("Results") or []):
                member_oid = result.get("ObjectIdentifier")
                if member_oid:
                    batch.append({"member": member_oid, "computer": comp_oid})
            break  # Only process the -544 group

        if not found_admin_group:
            # No -544 group found in LocalGroups — count as uncollected
            uncollected += 1

    if not batch:
        return 0, uncollected

    query = """
    UNWIND $batch AS row
    MERGE (m {objectid: row.member, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET m.source = 'bloodhound'
    WITH m, row
    MERGE (c {objectid: row.computer, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET c.source = 'bloodhound'
    MERGE (m)-[:AdminTo]->(c)
    """
    await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
    return len(batch), uncollected


async def _ingest_gplink(session, all_records: dict, org_id: str, engagement_id: str) -> int:
    """GpLink from OU/Domain Links arrays."""
    batch = []
    for meta_type in ("ous", "domains"):
        for rec in all_records.get(meta_type, []):
            obj_oid = rec.get("ObjectIdentifier")
            if not obj_oid:
                continue
            for link in (rec.get("Links") or []):
                gpo_guid = link.get("GUID")
                if gpo_guid:
                    batch.append({"gpo": gpo_guid, "target": obj_oid})

    if not batch:
        return 0

    query = """
    UNWIND $batch AS row
    MERGE (g {objectid: row.gpo, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET g.source = 'bloodhound'
    WITH g, row
    MERGE (t {objectid: row.target, org_id: $org_id, engagement_id: $engagement_id})
    ON CREATE SET t.source = 'bloodhound'
    MERGE (g)-[:GpLink]->(t)
    """
    await session.run(query, batch=batch, org_id=org_id, engagement_id=engagement_id)
    return len(batch)


# ═══════════════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════════

async def ingest_bloodhound(folder_path: str, org_id: str, engagement_id: str) -> dict:
    """Ingest a SharpHound CE v6 export folder into Neo4j.
    Args:
        folder_path:   Path to directory containing per-type JSON files.
        org_id:        Organization UUID — included in every MERGE key for tenant isolation.
        engagement_id: Engagement UUID — included in every MERGE key for tenant isolation.
    Returns:
        Summary dict with counts of nodes, relationships, skipped ACE types, etc.
    """
    log.info("Loading SharpHound export from: %s (org=%s engagement=%s)", folder_path, org_id, engagement_id)
    all_records = _load_folder(folder_path)
    node_counts = {}
    rel_counts = {}
    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        # ── Pass 1: Create all nodes ──────────────────────────────────────
        log.info("── Pass 1: Merging nodes ──")
        for meta_type in OBJECT_TYPES_ORDER:
            records = all_records.get(meta_type, [])
            if records:
                label = NODE_CONFIG[meta_type][0]
                count = await _ingest_nodes(ts, meta_type, records, org_id, engagement_id)
                node_counts[label] = count
        # ── Pass 2: Create all relationships ──────────────────────────────
        log.info("── Pass 2: Merging relationships ──")
        # MemberOf (from groups)
        log.info("  Processing MemberOf...")
        rel_counts["MemberOf"] = await _ingest_memberof(ts, all_records.get("groups", []), org_id, engagement_id)
        log.info("  %-22s  %4d edges", "MemberOf", rel_counts["MemberOf"])
        # ACL relationships (from all types)
        log.info("  Processing ACLs...")
        ace_counts, skipped_rights = await _ingest_aces(ts, all_records, org_id, engagement_id)
        rel_counts.update(ace_counts)
        # Contains (from all types via ContainedBy)
        log.info("  Processing Contains...")
        rel_counts["Contains"] = await _ingest_contains(ts, all_records, org_id, engagement_id)
        log.info("  %-22s  %4d edges", "Contains", rel_counts["Contains"])
        # HasSession (from computers)
        log.info("  Processing HasSession...")
        has_session_count, uncollected_sessions = await _ingest_hassession(
            ts, all_records.get("computers", []), org_id, engagement_id
        )
        rel_counts["HasSession"] = has_session_count
        log.info("  %-22s  %4d edges  (%d computers uncollected)",
                 "HasSession", has_session_count, uncollected_sessions)
        # AdminTo (from computers)
        log.info("  Processing AdminTo...")
        admin_to_count, uncollected_localgroups = await _ingest_adminto(
            ts, all_records.get("computers", []), org_id, engagement_id
        )
        rel_counts["AdminTo"] = admin_to_count
        log.info("  %-22s  %4d edges  (%d computers uncollected)",
                 "AdminTo", admin_to_count, uncollected_localgroups)
        # GpLink (from OUs and Domains)
        log.info("  Processing GpLink...")
        rel_counts["GpLink"] = await _ingest_gplink(ts, all_records, org_id, engagement_id)
        log.info("  %-22s  %4d edges", "GpLink", rel_counts["GpLink"])
    # Ensure all expected rel types appear in output even if 0
    for rt in ["MemberOf", "GenericAll", "GenericWrite", "WriteDacl",
               "WriteOwner", "Owns", "AllExtendedRights", "ForceChangePassword",
               "AddMember", "Contains", "HasSession", "AdminTo", "GpLink"]:
        rel_counts.setdefault(rt, 0)
    if skipped_rights:
        log.info("Skipped ACE RightName values (not handled): %s", sorted(skipped_rights))
    # NOTE: GPOChanges and ChildObjects fields on OU/Domain/Container are not
    # processed — they were empty/redundant with ContainedBy in the sample data.
    # May need revisiting if a future real export populates them with
    # non-redundant data.
    result = {
        "nodes_ingested": node_counts,
        "relationships_ingested": rel_counts,
        "skipped_ace_types": sorted(skipped_rights),
        "computers_with_uncollected_sessions": uncollected_sessions,
        "computers_with_uncollected_localgroups": uncollected_localgroups,
    }
    log.info("─── Ingestion complete ───")
    return result

# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pprint

    if len(sys.argv) < 4:
        print("Usage: python -m etl.bloodhound <path-to-sharphound-folder> <org_id> <engagement_id>")
        sys.exit(1)

    folder = sys.argv[1]
    if not os.path.isdir(folder):
        print(f"Error: {folder} is not a directory")
        sys.exit(1)

    import asyncio
    result = asyncio.run(ingest_bloodhound(folder, org_id=sys.argv[2], engagement_id=sys.argv[3]))

    print("\n═══ INGESTION SUMMARY ═══")
    pprint.pprint(result)
