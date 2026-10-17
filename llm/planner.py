"""
llm/planner.py — Campaign plan generation using RAG + GNN Path Scoring + LLM

Combines GNN path scoring (Neo4j embeddings) + RAG context (Qdrant)
+ LLM generation (LLMProvider) to produce the final campaign plan.
"""

from typing import List, Dict, Any, Optional
from llm.provider import get_provider

# llm.rag and gnn.init_gat pull in sentence-transformers / torch at import
# time — keep them lazy so the API boots without the ML stack installed.
# Each function that needs them does a local import on first call.

PROMPT_TEMPLATE = """You are a red team planning assistant for INSA, Ethiopia's national cybersecurity agency. Generate a structured campaign plan.

This campaign emulates {actor_name} specifically based on matching technique signatures. Do not attribute techniques to other actors.

ATTACK PATH IDENTIFIED:
{path_description}

RELEVANT THREAT INTELLIGENCE:
{retrieved_context}

Write a campaign plan with these sections:
1. PHASE 1 — Initial Access
2. PHASE 2 — Privilege Escalation
3. PHASE 3 — Lateral Movement
4. DETECTION HYPOTHESES

For each phase specify: technique used, objective, rationale tied to the threat actor profile above. Keep total response under 400 words. Be specific and technical, not generic."""

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


async def find_and_score_paths(source: str, target: str, org_id: str, engagement_id: str, max_hops: int = 5) -> List[Dict[str, Any]]:
    """
    Find paths from source (User) to target (Computer) and score them using PathGAT.
    """
    from gnn.init_gat import score_candidate_path, get_gat_state  # lazy ML import
    from graph.tenant_session import TenantSession

    # Get GAT state for this tenant
    state = await get_gat_state(org_id, engagement_id)
    name_to_idx = state["name_to_idx"]

    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        query = """
            MATCH p = (src:User {name: $source, org_id: $org_id})-[*1..5]->(dst:Computer)
            WHERE (dst.name = $target OR $target IS NULL OR dst.objectid = $target)
              AND dst.org_id = $org_id
            RETURN 
                [n in nodes(p) | coalesce(n.name, n.objectid, n.actor_id, n.technique_id)] AS path_nodes,
                [r in relationships(p) | type(r)] AS rel_types,
                length(p) AS hops
            ORDER BY hops
            LIMIT 10
        """
        result = await ts.run(query, source=source, target=target)
        paths = [record async for record in result]

    if not paths:
        return []

    scored_paths = []
    for path in paths:
        nodes_list = path["path_nodes"]
        rels_list = path["rel_types"]
        gat_score = await score_candidate_path(nodes_list, rels_list, org_id, engagement_id)
        scored_paths.append({
            "score": gat_score,
            "nodes": nodes_list,
            "rels": rels_list,
            "hops": path["hops"]
        })

    scored_paths.sort(key=lambda x: x["score"], reverse=True)
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

    print(f"Retrieving threat intelligence context from Qdrant for query: '{rag_query}'...")
    from llm.rag import retrieve_context  # lazy ML import (sentence-transformers)
    rag_results = retrieve_context(rag_query, top_k=3)
    
    # Format retrieved context
    context_parts = []
    for item in rag_results:
        context_parts.append(f"=== {item['type'].upper()}: {item['name']} ===\n{item['text']}")
    retrieved_context = "\n\n".join(context_parts)

    # Build prompt
    prompt = PROMPT_TEMPLATE.format(
        actor_name=actor_name,
        path_description=path_description,
        retrieved_context=retrieved_context
    )

    print("Generating campaign plan using LLM...")
    try:
        provider = get_provider()
        plan_text = provider.generate(prompt, max_tokens=4000)
        return plan_text
    except Exception as e:
        print(f"LLM generation failed: {e}")
        # Fallback to templated plan
        return _templated_plan(scored_paths)


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


def _templated_plan(scored_paths: List[Dict[str, Any]]) -> str:
    """Fallback templated plan when LLM is unavailable."""
    top_path = scored_paths[0]
    path_nodes = top_path['nodes']
    target_node = path_nodes[-1] if path_nodes else ""
    domain = _extract_domain(target_node)
    
    return f"""[LLM unavailable — showing templated plan]

=== CAMPAIGN PLAN ===
Target Domain: {domain}
Method: Templated Fallback

1. PHASE 1 — Initial Access
   Technique: Spearphishing Attachment (T1566.001)
   Objective: Compromise {path_nodes[0]}
   Rationale: HR and domain user accounts are highly vulnerable to spearphishing.

2. PHASE 2 — Privilege Escalation
   Technique: Valid Accounts (T1078.002) / GenericWrite Abuse
   Objective: Abuse GenericWrite on service account to escalate privileges.
   Rationale: The path GNN score is {top_path['score']:.4f}.

3. PHASE 3 — Lateral Movement
   Technique: AdminTo Abuse / Remote Services
   Objective: Move to target computer {path_nodes[-1]}
   Rationale: Leverage acquired domain admin credentials to access the target system.

4. DETECTION HYPOTHESES
   - Alert on unexpected credential modifications for service accounts.
   - Alert on unusual lateral movement sessions to {path_nodes[-1]}.
"""


# Backward compatibility wrapper for existing code
async def generate_plan(paths: List[Dict], sector: str = "government", use_llm: bool = True, org_id: str = "", engagement_id: str = "") -> str:
    """Backward compatible wrapper for old planner interface."""
    if not paths:
        return "No paths provided."
    if not use_llm:
        return _templated_plan(paths)
        
    try:
        # Use the first path to generate
        top_path = paths[0]
        source = top_path["nodes"][0]
        target = top_path["nodes"][-1]
        return await generate_campaign_plan(source, target, org_id=org_id, engagement_id=engagement_id)
    except Exception as e:
        print(f"Error in generate_plan wrapper: {e}")
        return _templated_plan(paths)