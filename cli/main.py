#!/usr/bin/env python3
"""
cli/main.py — ETHIO-RTAP Command Line Client

A professional CLI wrapping the Red Team Planning Platform API.
Communicates exclusively via HTTP requests to the FastAPI backend.

Usage:
    python -m cli.main auth login
    python -m cli.main graph stats
    python -m cli.main actors list
    python -m cli.main paths <source> <target>
    python -m cli.main plan generate <source> <target>
    python -m cli.main ingest bloodhound <zip_path>
"""

import json
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

# =============================================================================
# Constants
# =============================================================================

BASE_URL = "http://localhost:8000"
TOKEN_DIR = Path.home() / ".rtap"
TOKEN_FILE = TOKEN_DIR / "token.json"

console = Console()

# =============================================================================
# Typer app hierarchy
# =============================================================================

app = typer.Typer(
    name="rtap",
    help="ETHIO-RTAP — Red Team Planning Platform CLI",
    no_args_is_help=True,
)

auth_app = typer.Typer(help="Authentication commands", no_args_is_help=True)
graph_app = typer.Typer(help="Graph database commands", no_args_is_help=True)
actors_app = typer.Typer(help="Threat actor commands", no_args_is_help=True)
plan_app = typer.Typer(help="Campaign plan commands", no_args_is_help=True)
ingest_app = typer.Typer(help="Data ingestion commands", no_args_is_help=True)

app.add_typer(auth_app, name="auth")
app.add_typer(graph_app, name="graph")
app.add_typer(actors_app, name="actors")
app.add_typer(plan_app, name="plan")
app.add_typer(ingest_app, name="ingest")

# =============================================================================
# Token management
# =============================================================================


def save_token(access_token: str, token_type: str, username: str, expires_in: int) -> None:
    """Save JWT token to disk with restricted permissions."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    expires_at = time.time() + expires_in
    data = {
        "access_token": access_token,
        "token_type": token_type,
        "username": username,
        "expires_at": expires_at,
    }
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    # Restrict to owner-only read/write (credential file)
    os.chmod(TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0o600


def load_token() -> Optional[Dict[str, Any]]:
    """Load cached token, or None if missing."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def clear_token() -> None:
    """Delete cached token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def get_auth_headers() -> Dict[str, str]:
    """
    Load token and return auth headers. Exits with a clear message if
    the token is missing or expired (client-side check).
    """
    token = load_token()
    if token is None:
        console.print("[bold red]✗[/] Not logged in. Run: [bold]rtap auth login[/]")
        raise typer.Exit(code=1)

    if time.time() >= token["expires_at"]:
        console.print(
            "[bold red]✗[/] Your session has expired. Run: [bold]rtap auth login[/]"
        )
        raise typer.Exit(code=1)

    return {"Authorization": f"Bearer {token['access_token']}"}


# =============================================================================
# HTTP helper
# =============================================================================


def api_request(
    method: str,
    path: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict] = None,
    params: Optional[Dict] = None,
    files: Optional[Dict] = None,
    timeout: float = 60.0,
) -> httpx.Response:
    """
    Make an HTTP request to the API with standardized error handling.
    Returns the httpx.Response on success, or exits cleanly on errors.
    """
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            files=files,
            timeout=timeout,
        )
    except httpx.ConnectError:
        console.print(
            "[bold red]✗[/] Could not connect to the API at "
            f"[bold]{BASE_URL}[/] — is it running? "
            "([dim]python3 start_api.py[/dim])"
        )
        raise typer.Exit(code=1)
    except httpx.TimeoutException:
        console.print("[bold red]✗[/] Request timed out. The server may be overloaded.")
        raise typer.Exit(code=1)

    # Handle error responses
    if response.status_code == 401:
        detail = _extract_detail(response)
        # Could be bad credentials on login, or expired/invalid token
        console.print(f"[bold red]✗[/] Authentication failed: {detail}")
        console.print("  Run: [bold]rtap auth login[/]")
        raise typer.Exit(code=1)

    if response.status_code == 403:
        detail = _extract_detail(response)
        console.print(f"[bold red]✗[/] Insufficient permissions: {detail}")
        raise typer.Exit(code=1)

    if response.status_code >= 400:
        detail = _extract_detail(response)
        console.print(f"[bold red]✗[/] API error ({response.status_code}): {detail}")
        raise typer.Exit(code=1)

    return response


def _extract_detail(response: httpx.Response) -> str:
    """Extract the 'detail' field from a JSON error response."""
    try:
        body = response.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
        return json.dumps(body)
    except Exception:
        return response.text or f"HTTP {response.status_code}"


# =============================================================================
# Helpers
# =============================================================================


def truncate_name(name: str, max_len: int = 30) -> str:
    """Truncate long AD node names for table display."""
    if name and len(name) > max_len:
        return name[: max_len - 3] + "..."
    return name or ""


def format_path_compact(nodes: List[str], rels: List[str], truncate: bool = True) -> str:
    """Build a compact path representation: NODE -[REL]-> NODE -[REL]-> NODE"""
    parts = []
    for i, node in enumerate(nodes):
        display = truncate_name(node) if truncate else node
        parts.append(display)
        if i < len(rels):
            parts.append(f"-[{rels[i]}]->")
    return " ".join(parts)


def risk_label(rank: int) -> str:
    """Return rich-formatted risk label based on rank position."""
    if rank == 1:
        return "[bold red]HIGH[/]"
    elif rank == 2:
        return "[bold yellow]MEDIUM[/]"
    else:
        return "LOW"


def format_timestamp(ts_str: str) -> str:
    """Format an ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        return ts_str or "unknown"


# =============================================================================
# AUTH COMMANDS
# =============================================================================


@auth_app.command("login")
def auth_login(
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Username"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password"),
) -> None:
    """Authenticate with the API and cache the token."""
    if username is None:
        username = typer.prompt("Username")
    if password is None:
        password = typer.prompt("Password", hide_input=True)

    response = api_request(
        "POST",
        "/auth/login",
        json_body={"username": username, "password": password},
    )

    data = response.json()
    save_token(
        access_token=data["access_token"],
        token_type=data.get("token_type", "bearer"),
        username=username,
        expires_in=data["expires_in"],
    )

    hours = data["expires_in"] // 3600
    console.print(
        f"[bold green]✓[/] Logged in as [bold]{username}[/] "
        f"(token expires in {hours}h)"
    )


@auth_app.command("whoami")
def auth_whoami() -> None:
    """Show the currently cached user and token status."""
    token = load_token()
    if token is None:
        console.print("[bold red]✗[/] Not logged in. Run: [bold]rtap auth login[/]")
        raise typer.Exit(code=1)

    username = token.get("username", "unknown")
    expires_at = token.get("expires_at", 0)
    now = time.time()
    remaining = expires_at - now
    token_prefix = token.get("access_token", "")[:12] + "..."

    table = Table(title="Session Info", show_header=False, border_style="dim")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Username", username)
    table.add_row("Token", f"[dim]{token_prefix}[/dim]")

    if remaining <= 0:
        table.add_row("Status", "[bold red]EXPIRED[/]")
        table.add_row("Expired", _format_seconds_ago(-remaining) + " ago")
    else:
        table.add_row("Status", "[bold green]ACTIVE[/]")
        table.add_row("Expires in", _format_seconds_ago(remaining))
        expiry_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        table.add_row("Expires at", expiry_dt.strftime("%Y-%m-%d %H:%M:%S UTC"))

    console.print(table)


def _format_seconds_ago(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    seconds = abs(seconds)
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"


@auth_app.command("logout")
def auth_logout() -> None:
    """Clear the cached authentication token."""
    clear_token()
    console.print("[bold green]✓[/] Logged out")


# =============================================================================
# GRAPH COMMANDS
# =============================================================================


@graph_app.command("stats")
def graph_stats() -> None:
    """Display node and relationship counts from the graph database."""
    headers = get_auth_headers()
    response = api_request("GET", "/graph/stats", headers=headers)
    data = response.json()

    # Node counts table
    nodes = data.get("nodes", {})
    if nodes:
        node_table = Table(title="Node Counts", border_style="dim")
        node_table.add_column("Type", style="bold")
        node_table.add_column("Count", justify="right")

        sorted_nodes = sorted(nodes.items(), key=lambda x: x[1], reverse=True)
        for node_type, count in sorted_nodes:
            node_table.add_row(node_type, f"{count:,}")

        total = sum(nodes.values())
        node_table.add_section()
        node_table.add_row("[bold]Total[/]", f"[bold]{total:,}[/]")
        console.print(node_table)
    else:
        console.print("[dim]No nodes in graph[/]")

    console.print()

    # Relationship counts table
    rels = data.get("relationships", {})
    if rels:
        rel_table = Table(title="Relationship Counts", border_style="dim")
        rel_table.add_column("Type", style="bold")
        rel_table.add_column("Count", justify="right")

        sorted_rels = sorted(rels.items(), key=lambda x: x[1], reverse=True)
        for rel_type, count in sorted_rels:
            rel_table.add_row(rel_type, f"{count:,}")

        total = sum(rels.values())
        rel_table.add_section()
        rel_table.add_row("[bold]Total[/]", f"[bold]{total:,}[/]")
        console.print(rel_table)
    else:
        console.print("[dim]No relationships in graph[/]")


# =============================================================================
# ACTORS COMMANDS
# =============================================================================


@actors_app.command("list")
def actors_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full technique names"),
) -> None:
    """List known threat actors and their profiles."""
    headers = get_auth_headers()
    response = api_request("GET", "/actors", headers=headers)
    actors = response.json()

    if not actors:
        console.print("[dim]No threat actors found in the graph[/]")
        return

    table = Table(title="Threat Actors", border_style="dim")
    table.add_column("Actor", style="bold")
    table.add_column("Motivation")
    table.add_column("Sophistication")
    table.add_column("Techniques", overflow="fold")

    for actor in actors:
        name = actor.get("actor_name", "unknown")
        motivation = actor.get("motivation", "—")
        sophistication = actor.get("sophistication", "—")
        techniques = actor.get("techniques", [])

        if verbose:
            tech_display = ", ".join(techniques) if techniques else "—"
        else:
            count = len(techniques)
            tech_display = f"{count} technique{'s' if count != 1 else ''}" if count else "—"

        table.add_row(name, motivation, sophistication, tech_display)

    console.print(table)


# =============================================================================
# PATHS COMMAND
# =============================================================================


@app.command("paths")
def paths_cmd(
    source: str = typer.Argument(help="Source node (e.g. USER@DOMAIN)"),
    target: str = typer.Argument(help="Target node (e.g. COMPUTER.DOMAIN)"),
    max_results: int = typer.Option(10, "--max-results", "-n", help="Max paths to display"),
) -> None:
    """Find and score attack paths between two nodes."""
    headers = get_auth_headers()
    response = api_request(
        "GET", "/paths", headers=headers, params={"source": source, "target": target}
    )
    paths = response.json()

    if not paths:
        console.print(
            f"[dim]No paths found between [bold]{source}[/bold] and [bold]{target}[/bold][/dim]"
        )
        return

    # Truncate to max_results
    paths = paths[:max_results]

    table = Table(title=f"Attack Paths: {truncate_name(source)} → {truncate_name(target)}", border_style="dim")
    table.add_column("Rank", justify="center", width=4)
    table.add_column("Risk", justify="center", width=8)
    table.add_column("GAT Score", justify="right", width=10)
    table.add_column("Hops", justify="center", width=4)
    table.add_column("Path", overflow="fold")

    for rank, path in enumerate(paths, 1):
        score = path.get("score", 0)
        nodes = path.get("nodes", [])
        rels = path.get("rels", [])
        hops = path.get("hops", len(rels))

        path_str = format_path_compact(nodes, rels)
        label = risk_label(rank)

        table.add_row(str(rank), label, f"{score:.4f}", str(hops), path_str)

    console.print(table)


# =============================================================================
# PLAN COMMANDS
# =============================================================================


@plan_app.command("generate")
def plan_generate(
    source: str = typer.Argument(help="Source node (e.g. USER@DOMAIN)"),
    target: str = typer.Argument(help="Target node (e.g. COMPUTER.DOMAIN)"),
) -> None:
    """Generate a campaign plan for an attack path between two nodes."""
    headers = get_auth_headers()

    with console.status("[bold]Generating campaign plan...", spinner="dots"):
        response = api_request(
            "POST",
            "/plan/generate",
            headers=headers,
            json_body={"source": source, "target": target},
            timeout=120.0,  # LLM calls can be slow
        )

    data = response.json()
    plan_text = data.get("plan", "")
    generated_by = data.get("generated_by", "unknown")
    timestamp = format_timestamp(data.get("timestamp", ""))

    console.print()
    console.print(Panel(Markdown(plan_text), title="Campaign Plan", border_style="green"))
    console.print()
    console.print(
        f"[dim]Generated by: {generated_by} | {timestamp}[/dim]",
        justify="right",
    )


# =============================================================================
# INGEST COMMANDS
# =============================================================================


@ingest_app.command("bloodhound")
def ingest_bloodhound(
    zip_path: str = typer.Argument(help="Path to BloodHound/SharpHound .zip export"),
) -> None:
    """Upload and ingest BloodHound data from a SharpHound zip export."""
    # Validate file before attempting upload
    path = Path(zip_path)
    if not path.exists():
        console.print(f"[bold red]✗[/] File not found: [bold]{zip_path}[/]")
        raise typer.Exit(code=1)
    if not path.suffix.lower() == ".zip":
        console.print(
            f"[bold red]✗[/] File must be a .zip archive, got: [bold]{path.suffix}[/]"
        )
        raise typer.Exit(code=1)

    headers = get_auth_headers()

    with console.status("[bold]Uploading and ingesting BloodHound data...", spinner="dots"):
        with open(path, "rb") as f:
            response = api_request(
                "POST",
                "/ingest/bloodhound",
                headers=headers,
                files={"file": (path.name, f, "application/zip")},
                timeout=120.0,
            )

    data = response.json()

    # Handle dedup / skipped
    if data.get("skipped"):
        console.print(
            Panel(
                f"[yellow]⚠ File was already ingested (deduplicated)[/]\n"
                f"[dim]{data.get('message', '')}[/dim]",
                title="Skipped",
                border_style="yellow",
            )
        )
        return

    # Success — show summary tables
    console.print(f"[bold green]✓[/] {data.get('message', 'Ingestion complete')}\n")

    # Nodes ingested
    nodes = data.get("nodes_ingested", {})
    if nodes:
        node_table = Table(title="Nodes Ingested", border_style="dim")
        node_table.add_column("Type", style="bold")
        node_table.add_column("Count", justify="right")
        for ntype, count in sorted(nodes.items(), key=lambda x: x[1], reverse=True):
            node_table.add_row(ntype, f"{count:,}")
        total = sum(nodes.values())
        node_table.add_section()
        node_table.add_row("[bold]Total[/]", f"[bold]{total:,}[/]")
        console.print(node_table)
        console.print()

    # Relationships ingested
    rels = data.get("relationships_ingested", {})
    if rels:
        rel_table = Table(title="Relationships Ingested", border_style="dim")
        rel_table.add_column("Type", style="bold")
        rel_table.add_column("Count", justify="right")
        for rtype, count in sorted(rels.items(), key=lambda x: x[1], reverse=True):
            rel_table.add_row(rtype, f"{count:,}")
        total = sum(rels.values())
        rel_table.add_section()
        rel_table.add_row("[bold]Total[/]", f"[bold]{total:,}[/]")
        console.print(rel_table)
        console.print()

    # Warnings for skipped ACE types
    skipped_aces = data.get("skipped_ace_types", [])
    if skipped_aces:
        ace_list = ", ".join(skipped_aces)
        console.print(
            Panel(
                f"[yellow]Skipped ACE types:[/] {ace_list}",
                title="⚠ Warning",
                border_style="yellow",
            )
        )

    # Warnings for uncollected data
    uncollected_sessions = data.get("computers_with_uncollected_sessions", 0)
    uncollected_localgroups = data.get("computers_with_uncollected_localgroups", 0)
    if uncollected_sessions or uncollected_localgroups:
        lines = []
        if uncollected_sessions:
            lines.append(
                f"[yellow]{uncollected_sessions}[/] computer(s) with uncollected sessions"
            )
        if uncollected_localgroups:
            lines.append(
                f"[yellow]{uncollected_localgroups}[/] computer(s) with uncollected local groups"
            )
        console.print(
            Panel(
                "\n".join(lines),
                title="⚠ Incomplete Collection",
                border_style="yellow",
            )
        )


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    app()
