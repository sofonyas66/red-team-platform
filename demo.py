#!/usr/bin/env python3
"""
demo.py — End-to-end demonstration of the Red Team Planning Platform

Run: python demo.py
"""

import time
import sys
import argparse
from datetime import datetime
import numpy as np
from graph.connection import driver

# Import Phase 4 modules
try:
    from llm.planner import generate_plan
    PLANNER_AVAILABLE = True
except ImportError as e:
    PLANNER_AVAILABLE = False
    print(f"[Warning] Planner not available: {e}")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def print_section(title):
    """Print a section header with a small pause."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")
    time.sleep(0.5)


def print_subsection(title):
    """Print a subsection header."""
    print(f"\n--- {title} ---")
    time.sleep(0.5)


def check_neo4j_connection():
    """Verify Neo4j is accessible."""
    try:
        with driver.session() as session:
            session.run("RETURN 1")
        return True
    except Exception as e:
        print(f"\n❌ Neo4j is not running. Start with: docker start neo4j")
        print(f"   Error: {e}")
        return False


# ============================================================================
# STEP 1: GRAPH STATE
# ============================================================================

def step1_graph_state():
    print_section("STEP 1 — GRAPH STATE")
    
    with driver.session() as session:
        # Nodes
        node_result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS type, count(n) AS count
            ORDER BY count DESC
        """)
        nodes = {r["type"]: r["count"] for r in node_result}
        
        # Relationships
        rel_result = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS type, count(r) AS count
            ORDER BY count DESC
        """)
        rels = {r["type"]: r["count"] for r in rel_result}
        
        total_nodes = sum(nodes.values())
        total_rels = sum(rels.values())
        
        print(f"\nNodes:")
        for t in ["User", "Computer", "Group", "Domain", "ThreatActor", "Technique", "Sector"]:
            if t in nodes:
                print(f"  {t:<12}: {nodes[t]}")
        print(f"  Total: {total_nodes} nodes")
        
        print(f"\nRelationships:")
        for rel_type, count in rels.items():
            print(f"  {rel_type:<12}: {count}")
        print(f"  Total: {total_rels} relationships")


# ============================================================================
# STEP 2: ATTACK PATH DISCOVERY
# ============================================================================

def step2_attack_paths():
    print_section("STEP 2 — ATTACK PATH DISCOVERY")
    
    source_name = "hr_user01@ETHBANK.LOCAL"
    print(f"\nSource: {source_name}")
    print("Scanning for paths to domain computers...")
    
    with driver.session() as session:
        result = session.run("""
            MATCH p = (src:User {name: $source})-[*1..5]->(dst:Computer)
            RETURN 
                [n in nodes(p) | coalesce(n.name, n.objectid, n.actor_id, n.technique_id)] AS path_nodes,
                [r in relationships(p) | type(r)] AS rel_types,
                length(p) AS hops
            ORDER BY hops
            LIMIT 10
        """, source=source_name)
        
        paths = list(result)
        
        if not paths:
            print("\n⚠️  No paths found to Computer nodes within 5 hops")
            return []
        
        print(f"\nFound {len(paths)} path(s):\n")
        
        for i, path in enumerate(paths, 1):
            nodes_list = path["path_nodes"]
            rels_list = path["rel_types"]
            hops = path["hops"]
            
            print(f"Path {i} ({hops} hops):")
            for j, node_name in enumerate(nodes_list):
                print(f"  {node_name}")
                if j < len(rels_list):
                    print(f"    -[{rels_list[j]}]->")
            print()
        
        return paths


# ============================================================================
# STEP 3: GNN PATH SCORING
# ============================================================================

def step3_score_paths(paths):
    print_section("STEP 3 — GNN PATH SCORING")
    
    if not paths:
        print("No paths to score.")
        return []
    
    print("Scoring paths by structural similarity...")
    
    with driver.session() as session:
        # Fetch all embeddings at once
        emb_result = session.run("""
            MATCH (n) WHERE n.embedding IS NOT NULL
            RETURN 
                coalesce(n.name, n.objectid, n.actor_id, n.technique_id) AS name,
                n.embedding AS embedding
        """)
        
        # Build name -> embedding lookup
        embeddings = {}
        for record in emb_result:
            embeddings[record["name"]] = record["embedding"]
        
        print(f"  Loaded {len(embeddings)} node embeddings")
        
        # Score each path
        scored_paths = []
        for path in paths:
            nodes_list = path["path_nodes"]
            rels_list = path["rel_types"]
            
            similarities = []
            for i in range(len(nodes_list) - 1):
                name_a = nodes_list[i]
                name_b = nodes_list[i + 1]
                
                if name_a in embeddings and name_b in embeddings:
                    sim = cosine_similarity(embeddings[name_a], embeddings[name_b])
                    similarities.append(sim)
                else:
                    similarities.append(0.0)
            
            avg_score = np.mean(similarities) if similarities else 0.0
            
            scored_paths.append({
                "score": avg_score,
                "nodes": nodes_list,
                "rels": rels_list,
                "similarities": similarities
            })
        
        # Sort by score descending
        scored_paths.sort(key=lambda x: x["score"], reverse=True)
        
        # Print ranked results
        print()
        for rank, sp in enumerate(scored_paths, 1):
            if rank == 1:
                risk = "HIGH"
            elif rank == 2:
                risk = "MEDIUM"
            else:
                risk = "LOW"
            print(f"Rank {rank} — Score: {sp['score']:.4f}  (Risk: {risk})")
            print("  (Score is relative — Rank 1 is the highest-probability path in this environment)")
            for j, node_name in enumerate(sp["nodes"]):
                print(f"  {node_name}")
                if j < len(sp["rels"]):
                    sim = sp["similarities"][j]
                    print(f"    -[{sp['rels'][j]}]->  (cosine: {sim:.4f})")
            print()
        
        return scored_paths


# ============================================================================
# STEP 4: THREAT ACTOR CORRELATION
# ============================================================================

def step4_threat_actor_correlation(top_path):
    print_section("STEP 4 — THREAT ACTOR CORRELATION")
    
    if not top_path:
        print("No top path to correlate.")
        return
    
    # Map relationship types to ATT&CK techniques
    rel_to_technique = {
        "GenericWrite": "T1078.002",  # Valid Accounts: Domain Accounts
        "AdminTo": "T1059.001",        # Command and Scripting Interpreter: PowerShell (lateral movement)
        "MemberOf": "T1069.002",       # Permission Groups Discovery
        "HasSession": "T1021.004",     # Pass the Hash
        "GenericAll": "T1098",         # Account Manipulation
        "WriteDacl": "T1222.001",      # File and Directory Permissions Modification
        "Contains": "T1083",           # File and Directory Discovery
        "GpLink": "T1484.001",         # Group Policy Modification
    }
    
    # Get unique techniques from top path
    techniques_in_path = set()
    for rel in top_path["rels"]:
        if rel in rel_to_technique:
            techniques_in_path.add(rel_to_technique[rel])
    
    print(f"Techniques in top path: {', '.join(sorted(techniques_in_path))}")
    
    # Query threat actors using these techniques
    with driver.session() as session:
        result = session.run("""
            MATCH (a:ThreatActor)-[:USES]->(t:Technique)
            WHERE t.technique_id IN $techniques
            RETURN a.name AS actor_name, a.motivation AS motivation, 
                   a.sophistication AS sophistication,
                   collect(t.name) AS techniques
            ORDER BY a.name
        """, techniques=list(techniques_in_path))
        
        actors = list(result)
        
        if not actors:
            print("\n⚠️  No matching threat actors found in ETI-Core")
            return
        
        print("\nTechniques in top path match known actor profile:\n")
        
        for actor in actors:
            print(f"Actor    : {actor['actor_name']}")
            print(f"Type     : State-affiliated" if "Horus" in actor['actor_name'] else "Financially motivated")
            print(f"Motivation: {actor['motivation']}")
            print(f"Sophistication: {actor['sophistication']}")
            print(f"Matching techniques:")
            for tech in actor["techniques"]:
                print(f"  - {tech}")
            print()


# ============================================================================
# STEP 5: CAMPAIGN PLAN (using Phase 4 RAG + Planner)
# ============================================================================

def step5_campaign_plan(scored_paths):
    print_section("STEP 5 — CAMPAIGN PLAN")
    
    if not scored_paths:
        print("No attack path found to generate plan.")
        return
    
    if PLANNER_AVAILABLE:
        print("  Generating plan via RAG + Planner...")
        # Determine sector from threat actor correlation
        sector = "financial"  # Could be inferred from actor targets
        plan = generate_plan(scored_paths, sector=sector, use_llm=True)
        print(plan)
    else:
        print("  [Planner not available — using basic template]")
        # Minimal fallback
        top_path = scored_paths[0]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plan = f"""
=== CAMPAIGN PLAN ===
Generated: {now}
Target Domain: ETHBANK.LOCAL
Method: Basic Template

PHASE 1 — INITIAL ACCESS
  Technique : Spearphishing Attachment (T1566.001)
  Objective : Compromise {top_path['nodes'][0]}

PHASE 2 — PRIVILEGE ESCALATION  
  Technique : Valid Accounts — Domain Accounts (T1078.002)
  Objective : Abuse GenericWrite on {top_path['nodes'][1]}

PHASE 3 — LATERAL MOVEMENT
  Technique : AdminTo abuse
  Objective : Move from {top_path['nodes'][1]} to {top_path['nodes'][2]}

==============================================
Platform: Red Team Planning and Analysis Platform
INSA Ethio Cyber Talent Program — Red Team Track
==============================================
""".strip()
        print(plan)


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Red Team Planning Platform Demo")
    parser.add_argument("--fast", action="store_true", help="Skip pauses between sections")
    parser.add_argument("--step", type=int, choices=[1,2,3,4,5], help="Run only a specific step")
    args = parser.parse_args()
    
    # Override sleep if --fast
    if args.fast:
        global time
        original_sleep = time.sleep
        time.sleep = lambda x: None
    
    print("=" * 60)
    print("  RED TEAM PLANNING PLATFORM — DEMO")
    print("  INSA Ethio Cyber Talent Program")
    print("=" * 60)
    
    # Check Neo4j
    if not check_neo4j_connection():
        sys.exit(1)
    
    steps = {
        1: ("STEP 1 — GRAPH STATE", step1_graph_state),
        2: ("STEP 2 — ATTACK PATH DISCOVERY", step2_attack_paths),
        3: ("STEP 3 — GNN PATH SCORING", step3_score_paths),
        4: ("STEP 4 — THREAT ACTOR CORRELATION", step4_threat_actor_correlation),
        5: ("STEP 5 — CAMPAIGN PLAN", step5_campaign_plan),
    }
    
    if args.step:
        # Run single step
        step_num = args.step
        if step_num in steps:
            title, func = steps[step_num]
            if step_num == 4:
                # Step 4 needs top_path from step 3
                paths = step2_attack_paths()
                scored = step3_score_paths(paths)
                func(scored[0] if scored else None)
            elif step_num == 5:
                # Step 5 needs scored paths from step 3
                paths = step2_attack_paths()
                scored = step3_score_paths(paths)
                func(scored)
            else:
                func()
        else:
            print(f"Unknown step: {args.step}")
        return
    
    # Run all steps
    # Step 1: Graph State
    step1_graph_state()
    if not args.fast: time.sleep(0.5)
    
    # Step 2: Attack Path Discovery
    paths = step2_attack_paths()
    if not args.fast: time.sleep(0.5)
    
    # Step 3: GNN Path Scoring
    scored_paths = step3_score_paths(paths)
    if not args.fast: time.sleep(0.5)
    
    # Step 4: Threat Actor Correlation
    top_path = scored_paths[0] if scored_paths else None
    step4_threat_actor_correlation(top_path)
    if not args.fast: time.sleep(0.5)
    
    # Step 5: Campaign Plan
    step5_campaign_plan(scored_paths)
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()