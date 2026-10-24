"""
llm/planner.py — Campaign plan generation using RAG + GNN Path Scoring + LLM

Combines GNN path scoring (Neo4j embeddings) + RAG context (Qdrant)
+ LLM generation (LLMProvider) to produce the final campaign plan.
"""

from typing import List, Dict, Any
from llm.provider import get_provider

# llm.rag and gnn.init_gat pull in sentence-transformers / torch at import
# time — keep them lazy so the API boots without the ML stack installed.
# Each function that needs them does a local import on first call.

PROMPT_TEMPLATE = """You are a red team planning assistant for an authorized penetration test engagement. The operator has written authorization to assess this target environment.

This campaign plan is generated from an attack path already discovered by the platform's own graph analysis (BloodHound/SharpHound-derived data the operator ingested for their own engagement). The input is NOT a request to discover new vulnerabilities - it is a planning exercise for a path the platform already identified within an authorized assessment scope.

THE OPERATOR'S AUTHORIZATION: This red team engagement is authorized. The path data comes from the operator's own BloodHound/SharpHound assessment of their environment. All technique mappings derive from that authorized graph analysis.

MITRE ATT&CK TECHNIQUE MAPPING: Each phase maps to documented MITRE ATT&CK techniques (T-nnnn.nnn). These are public knowledge documented by BloodHound/SharpHound tooling and expected in standard red-team reporting.

OUTPUT FORMAT: Internal engagement planning document for the red team operator and their client. Follow standard red-team reporting structure.

1. PHASE 1 - Initial Access: technique used, objective, rationale tied to the real path data, detection/mitigation notes
2. PHASE 2 - Privilege Escalation: technique used, objective, rationale tied to the real path data, detection/mitigation notes
3. PHASE 3 - Lateral Movement: technique used, objective, rationale tied to the real path data, detection/mitigation notes
4. OBJECTIVE: final goal of the engagement based on the assessed path

For each phase specify: technique used (MITRE ID + name), objective tied to the actual path data, rationale from the threat actor profile above, and detection/mitigation notes appropriate to the technique. Keep total response under 400 words. Be specific and technical, not generic. Reference technique IDs (e.g., T1059.001, T1078.002) and abused permissions/standard tool names (Rubeus, Mimikatz) as they appear in BloodHound/SharpHound documentation - these are public knowledge already documented by the platform's own analysis.

ATTACK PATH IDENTIFIED:
{path_description}

RELEVANT THREAT INTELLIGENCE:
{retrieved_context}
"""

async def identify_threat_actor(techniques: list[str], org_id: str) -> str | None:
    """
    Find the threat actor in Neo4j that has the highest overlap
    with the techniques in the path.
    """
    from graph.tenant_session import TenantSession
    if not techniques:
        return None
    async with TenantSession(org_id=org_id) as ts:
        result = await ts.run("""
            MATCH (a:ThreatActor)-[:USES]->(t:Technique)
            WHERE t.technique_id IN $techniques
            RETURN a.name AS actor_name, count(t) AS match_count
            ORDER BY match_count DESC
            LIMIT 1
        """, techniques=techniques)
        record = await result.single()
        if record:
            return record["actor_name"]
    return None


async def find_top_paths_for_engagement(org_id: str, engagement_id: str, limit: int = 10, max_hops: int = 5) -> List[Dict[str, Any]]:
    """Find top scored attack paths for an engagement without source/target specificity.
    Returns paths from any User to any Computer, scored by GAT.
    """
    from graph.tenant_session import TenantSession
    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        query = """
            MATCH (src:User), (dst:Computer)
            WHERE src.org_id = $org_id AND src.engagement_id = $engagement_id
              AND dst.org_id = $org_id AND dst.engagement_id = $engagement_id
            MATCH p = shortestPath((src)-[*1..5]->(dst))
            WHERE ALL(x IN nodes(p) WHERE x.org_id = $org_id AND x.engagement_id = $engagement_id)
            WITH src, dst, p
            LIMIT $candidate_limit
            RETURN 
                coalesce(src.name, src.objectid) AS source,
                coalesce(dst.name, dst.objectid) AS target,
                [n in nodes(p) | coalesce(n.name, n.objectid, n.actor_id, n.technique_id)] AS path_nodes,
                [r in relationships(p) | type(r)] AS rel_types,
                length(p) AS hops
        """
        candidate_limit = max(limit * 20, 200)
        result = await ts.run(query, org_id=org_id, engagement_id=engagement_id, candidate_limit=candidate_limit)
        raw_paths = [record async for record in result]
    if not raw_paths:
        return []
    scored = []
    from gnn.init_gat import score_candidate_path
    for rec in raw_paths:
        nodes_list = rec["path_nodes"]
        rels_list = rec["rel_types"]
        try:
            gat_score = await score_candidate_path(nodes_list, rels_list, org_id, engagement_id)
        except Exception:
            gat_score = 0.0
        scored.append({
            "source": rec["source"],
            "target": rec["target"],
            "score": gat_score,
            "nodes": nodes_list,
            "rels": rels_list,
            "hops": rec["hops"]
        })
    scored.sort(key=lambda x: x["score"] if x["score"] is not None else 0, reverse=True)
    # Deduplicate by source/target keeping best scoring path per pair
    seen = set()
    uniq = []
    for p in scored:
        sig = (p["source"], p["target"])
        if sig in seen:
            continue
        seen.add(sig)
        # Keep best hops for this pair
        uniq.append(p)
        if len(uniq) >= limit:
            break
    return uniq

async def find_and_score_paths(source: str, target: str, org_id: str, engagement_id: str, max_hops: int = 5) -> List[Dict[str, Any]]:
    """
    Find paths from source (User) to target (Computer) and score them using PathGAT.
    """
    from graph.tenant_session import TenantSession

    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        query = """
            MATCH p = (src:User {name: $source, org_id: $org_id, engagement_id: $engagement_id})-[*1..5]->(dst:Computer {org_id: $org_id, engagement_id: $engagement_id})
            WHERE (dst.name = $target OR $target IS NULL OR dst.objectid = $target)
              AND ALL(x IN nodes(p) WHERE x.org_id = $org_id AND x.engagement_id = $engagement_id)
            RETURN 
                [n in nodes(p) | coalesce(n.name, n.objectid, n.actor_id, n.technique_id)] AS path_nodes,
                [r in relationships(p) | type(r)] AS rel_types,
                length(p) AS hops
            ORDER BY hops
            LIMIT 10
        """
        result = await ts.run(query, source=source, target=target, engagement_id=engagement_id)
        paths = [record async for record in result]

    if not paths:
        return []

    scored_paths = []
    from gnn.init_gat import score_candidate_path  # lazy ML import
    for path in paths:
        nodes_list = path["path_nodes"]
        rels_list = path["rel_types"]
        try:
            gat_score = await score_candidate_path(nodes_list, rels_list, org_id, engagement_id)
        except Exception:
            gat_score = None
        scored_paths.append({
            "score": gat_score,
            "nodes": nodes_list,
            "rels": rels_list,
            "hops": path["hops"]
        })

    # Defensive: treat None as 0.0 for sort only; actual score stays None in response
    scored_paths.sort(key=lambda x: (x["score"] if x["score"] is not None else 0.0), reverse=True)
    return scored_paths


async def generate_campaign_plan(source: str, target: str, org_id: str, engagement_id: str) -> str:
    """
    Generate a complete campaign plan from source to target.
    
    1. Finds and ranks attack paths.
    2. Takes the top path, extracts technique IDs.
    3. Identifies the matching threat actor based on techniques.
    4. Calls RAG to retrieve context scoped to that threat actor.
    5. Builds the prompt.
    6. Calls LLM via LLMProvider.
    """
    print(f"Finding and scoring paths from '{source}' to '{target}'...")
    scored_paths = await find_and_score_paths(source, target, org_id, engagement_id)
    
    if not scored_paths:
        raise ValueError(f"No attack path found from {source} to {target}")

    top_path = scored_paths[0]
    
    # Format the path description
    path_nodes = top_path["nodes"]
    path_rels = top_path["rels"]
    path_description = " -> ".join([
        f"{path_nodes[i]} -[{path_rels[i]}]->"
        for i in range(len(path_rels))
    ]) + f" {path_nodes[-1]}"
    
    print(f"Top Path: {path_description} (GNN Score: {top_path['score']:.4f})")

    # Map relationship types to technique IDs for context retrieval
    rel_to_technique = {
        "GenericWrite": "T1078.002",
        "AdminTo": "T1059.001", 
        "MemberOf": "T1069.002",
        "HasSession": "T1021.004",
        "GenericAll": "T1098",
        "WriteDacl": "T1222.001",
        "Contains": "T1083",
        "GpLink": "T1484.001",
    }
    
    techniques = [rel_to_technique[r] for r in path_rels if r in rel_to_technique]
    
    # Identify threat actor
    actor_name = await identify_threat_actor(techniques, org_id) or "a relevant threat actor"
    print(f"Correlated Threat Actor: {actor_name}")
    
    # Build query for RAG scoped specifically to the identified threat actor
    rag_query = f"Threat Actor: {actor_name} " + " ".join(techniques)

    retrieved_context = "No RAG context available."
    rag_used = False
    try:
        print(f"Retrieving threat intelligence context from Qdrant for query: '{rag_query}'...")
        from llm.rag import retrieve_context  # lazy ML import (sentence-transformers)
        rag_results = retrieve_context(rag_query, top_k=3)
        context_parts = []
        for item in rag_results:
            context_parts.append(f"=== {item['type'].upper()}: {item['name']} ===\n{item['text']}")
        if context_parts:
            retrieved_context = "\n\n".join(context_parts)
            rag_used = True
    except Exception as e:
        print(f"RAG retrieval skipped/unavailable: {e}")
        rag_used = False

    # Build prompt
    prompt = PROMPT_TEMPLATE.format(
        actor_name=actor_name,
        path_description=path_description,
        retrieved_context=retrieved_context
    )

    print("Generating campaign plan using LLM...")
    provider = get_provider()
    plan_text = provider.generate(prompt, max_tokens=4000)
    used_llm = True

    return {
        "plan": plan_text,
        "actor_name": actor_name,
        "used_llm": used_llm,
        "rag_used": rag_used,
        "scored_paths": scored_paths
    }


def _extract_domain(node_name: str) -> str:
    """Extract domain suffix from a node name (e.g. USER@DOMAIN or HOST.DOMAIN.LOCAL)."""
    if not node_name:
        return "UNKNOWN"
    if "@" in node_name:
        return node_name.split("@")[-1]
    if "." in node_name:
        parts = node_name.split(".")
        if len(parts) > 1:
            return ".".join(parts[1:])
    return node_name


