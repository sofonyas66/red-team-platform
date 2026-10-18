#!/usr/bin/env python3
"""
bootstrap.py — Single-command initialization script for the ETHIO-RTAP platform.

This script:
1. Starts the required Docker containers (neo4j, qdrant) if they are stopped.
2. Waits until Neo4j and Qdrant database engines are fully online and responsive.
3. Configures graph constraints and search indexes in Neo4j.
4. Loads the ETI-Core STIX 2.1 Threat Intel actors and techniques.
5. Populates the Qdrant vector database with embedded threat intelligence.

Usage: python bootstrap.py
Environment variables (from .env):
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
  QDRANT_URL
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Target hosts and ports from environment
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_HOST = NEO4J_URI.replace("bolt://", "").replace("neo4j://", "").split(":")[0]
NEO4J_PORT = int(NEO4J_URI.split(":")[-1])

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_HOST = QDRANT_URL.replace("http://", "").replace("https://", "").split(":")[0]
QDRANT_PORT = int(QDRANT_URL.split(":")[-1].split("/")[0])

COMPOSE_FILE = os.getenv("COMPOSE_FILE", "docker-compose.yml")
COMPOSE_CMD = os.getenv("COMPOSE_CMD", "docker compose")  # docker compose, docker-compose, podman compose


def check_port(host: str, port: int) -> bool:
    """Return True if port is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False


def check_http_health(url: str) -> bool:
    """Check HTTP health endpoint."""
    try:
        import urllib.request
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def run_compose_command(*args, check=True, capture=False):
    """Run a docker-compose command."""
    cmd = COMPOSE_CMD.split() + ["-f", COMPOSE_FILE] + list(args)
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, check=check)
            return True
    except subprocess.CalledProcessError as e:
        if check:
            print(f"[-] Command failed: {' '.join(cmd)}")
            if e.stderr:
                print(f"    Error: {e.stderr.strip()}")
        return False
    except FileNotFoundError:
        print(f"[-] Compose command not found: {COMPOSE_CMD}")
        print("    Tried: docker compose, docker-compose, podman compose")
        return False


def start_docker_services():
    """Start neo4j and qdrant containers using Docker/Podman Compose."""
    print("[*] Checking database infrastructure...")

    neo4j_up = check_port(NEO4J_HOST, NEO4J_PORT)
    qdrant_up = check_port(QDRANT_HOST, QDRANT_PORT)

    if neo4j_up and qdrant_up:
        print("[+] Neo4j and Qdrant are already running.")
        return True

    print("[*] Starting Neo4j and Qdrant containers...")
    if not run_compose_command("up", "-d", "--remove-orphans"):
        print("[-] Failed to start containers. Is Docker/Podman running?")
        print("    Try: systemctl --user start podman.socket  (for Podman on Linux)")
        return False

    # Wait for ports to become active
    retries = 30
    for i in range(retries):
        neo4j_up = check_port(NEO4J_HOST, NEO4J_PORT)
        qdrant_up = check_port(QDRANT_HOST, QDRANT_PORT)
        if neo4j_up and qdrant_up:
            print("[+] Database containers online and ports open.")
            return True
        print(f"[*] Waiting for database ports (retry {i+1}/{retries})...")
        time.sleep(2)

    print("[-] Timed out waiting for Neo4j/Qdrant to bind ports. Check container logs.")
    return False


async def _neo4j_ping() -> bool:
    """Single async Neo4j ping. Returns True if reachable."""
    from graph.connection import get_driver
    try:
        driver = get_driver()
        async with driver.session() as s:
            await s.run("RETURN 1")
        return True
    except Exception:
        return False


async def wait_for_neo4j_engine():
    """Wait for Neo4j internal engine to be responsive."""
    print("[*] Waiting for Neo4j internal engine to become responsive...")

    retries = 30
    for i in range(retries):
        ok = await _neo4j_ping()
        if ok:
            print("[+] Neo4j engine is ready.")
            return True
        if i == retries - 1:
            print("[-] Could not establish Neo4j session after retries.")
            print("    Verify credentials: NEO4J_USER / NEO4J_PASSWORD")
            return False
        time.sleep(2)
    return False


def wait_for_qdrant():
    """Wait for Qdrant to be fully ready."""
    print("[*] Waiting for Qdrant to be ready...")
    retries = 30
    for i in range(retries):
        if check_http_health(f"{QDRANT_URL}/healthz") or check_http_health(f"{QDRANT_URL}/"):
            print("[+] Qdrant is ready.")
            return True
        print(f"[*] Waiting for Qdrant (retry {i+1}/{retries})...")
        time.sleep(2)
    print("[-] Qdrant not ready after timeout.")
    return False


async def run_bootstrap():
    """Run all bootstrap steps in a single event loop."""
    # Wait for Neo4j engine
    if not await wait_for_neo4j_engine():
        return False

    if not wait_for_qdrant():
        return False

    # 2. Schema creation
    print("\n[*] Step 1: Initializing Neo4j Schema...")
    from graph.connection import get_driver
    from graph.schema import create_schema
    await create_schema()

    # 3. Load threat intel to Graph
    print("\n[*] Step 2: Loading ETI-Core Threat Intelligence...")
    from eti_core.loader import load_all
    await load_all()

    # 4. Populate Qdrant RAG context
    print("\n[*] Step 3: Generating RAG embeddings and loading Qdrant...")
    from llm.rag import embed_eti_core
    await embed_eti_core()

    print("\n" + "=" * 60)
    print(" Bootstrap Successful! Platform ready.")
    print("=" * 60)
    print("\nNext Steps:")
    print("  1. Ingest Active Directory SharpHound ZIP using the CLI:")
    print("     $ ./run.sh up")
    print("     $ python -m cli.main auth login --username admin")
    print("     $ python -m cli.main ingest bloodhound <path_to_zip>")
    print("  2. Train GNN embeddings on the ingested network topology:")
    print("     $ python -m gnn.embeddings")
    print("  3. Start the API server:")
    print("     $ python start_api.py")
    print("  4. Generate campaign playbooks:")
    print("     $ python -m cli.main plan generate <source_user> <target_computer>")
    print("=" * 60)
    return True


def main():
    print("=" * 60)
    print(" ETHIO-RTAP Platform Bootstrapper")
    print("=" * 60)

    # 1. Start databases (sync)
    if not start_docker_services():
        sys.exit(1)

    # Run all async bootstrap steps in single event loop
    import asyncio
    success = asyncio.run(run_bootstrap())
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()