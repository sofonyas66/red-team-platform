#!/usr/bin/env python3
"""
bootstrap.py — Single-command initialization script for the ETHIO-RTAP platform.

This script:
1. Starts the required Docker containers (neo4j, qdrant) if they are stopped.
2. Waits until Neo4j and Qdrant database engines are fully online and responsive.
3. Configures graph constraints and search indexes in Neo4j.
4. Loads the ETI-Core STIX 2.1 Threat Intel actors and techniques.
5. Populates the Qdrant vector database with embedded threat intelligence.
"""

import socket
import subprocess
import sys
import time

# Target hosts and ports
NEO4J_HOST, NEO4J_PORT = "127.0.0.1", 7687
QDRANT_HOST, QDRANT_PORT = "127.0.0.1", 6333


def check_port(host: str, port: int) -> bool:
    """Return True if port is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False


def start_docker_services():
    """Start neo4j and qdrant containers using Docker."""
    print("[*] Checking database infrastructure...")
    
    neo4j_up = check_port(NEO4J_HOST, NEO4J_PORT)
    qdrant_up = check_port(QDRANT_HOST, QDRANT_PORT)
    
    if neo4j_up and qdrant_up:
        print("[+] Neo4j and Qdrant are already running.")
        return

    print("[*] Starting Neo4j and Qdrant containers...")
    try:
        # Attempt to start the containers
        subprocess.run(["docker", "start", "neo4j", "qdrant"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("[-] Docker command not found. Please ensure Docker is running and Neo4j/Qdrant are online.")
        sys.exit(1)

    # Wait for ports to become active
    retries = 20
    for i in range(retries):
        neo4j_up = check_port(NEO4J_HOST, NEO4J_PORT)
        qdrant_up = check_port(QDRANT_HOST, QDRANT_PORT)
        if neo4j_up and qdrant_up:
            print("[+] Database containers online and ports open.")
            break
        print(f"[*] Waiting for database ports (retry {i+1}/{retries})...")
        time.sleep(2)
    else:
        print("[-] Timed out waiting for Neo4j/Qdrant to bind ports. Check container logs.")
        sys.exit(1)


def main():
    print("=" * 60)
    print(" ETHIO-RTAP Platform Bootstrapper ")
    print("=" * 60)

    # 1. Start databases
    start_docker_services()

    # Wait for engine initialization (Neo4j can take a few seconds after port opens)
    print("[*] Waiting for Neo4j internal engine to become responsive...")
    from graph.connection import driver
    retries = 15
    for i in range(retries):
        try:
            with driver.session() as s:
                s.run("RETURN 1")
            print("[+] Neo4j engine is ready.")
            break
        except Exception:
            time.sleep(2)
    else:
        print("[-] Could not establish a Neo4j session. Please verify credentials/connection.")
        sys.exit(1)

    # 2. Schema creation
    print("\n[*] Step 1: Initializing Neo4j Schema...")
    from graph.schema import create_schema
    create_schema()

    # 3. Load threat intel to Graph
    print("\n[*] Step 2: Loading ETI-Core Threat Intelligence...")
    from eti_core.loader import load_all
    load_all()

    # 4. Populate Qdrant RAG context
    print("\n[*] Step 3: Generating RAG embeddings and loading Qdrant...")
    from llm.rag import embed_eti_core
    embed_eti_core()

    print("\n" + "=" * 60)
    print(" Bootstrap Successful! Platform ready.")
    print("=" * 60)
    print("\nNext Steps:")
    print("  1. Ingest Active Directory SharpHound ZIP using the CLI:")
    print("     $ ./rtap ingest bloodhound <path_to_zip>")
    print("  2. Train GNN embeddings on the ingested network topology:")
    print("     $ python -m gnn.embeddings")
    print("  3. Start the API server:")
    print("     $ python start_api.py")
    print("  4. Generate campaign playbooks:")
    print("     $ ./rtap plan generate <source_user> <target_computer>")
    print("=" * 60)


if __name__ == "__main__":
    main()
