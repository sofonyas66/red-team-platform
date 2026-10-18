#!/usr/bin/env bash
# Fails CI if anything outside the approved files calls the driver directly.
set -euo pipefail

# Files permitted to call driver.session() directly:
#   graph/connection.py      — driver definition
#   graph/tenant_session.py  — TenantSession wrapper (wraps driver.session)
#   graph/schema.py          — schema bootstrap (runs once, not per-tenant)
#   etl/bloodhound.py        — ingestion pipeline (passes org_id/engagement_id through)
#   eti_core/loader.py       — threat-actor seed data (global, not per-tenant)
#   api/main.py              — health check endpoint only (RETURN 1, no engagement data)
#   bootstrap.py             — one-time setup script
#   gnn/embeddings.py        — GNN training (global model, not per-tenant query)
#   gnn/init_gat.py          — GNN init (global model)
#   llm/planner.py           — path scoring (TODO: migrate to TenantSession in Track 2.5)
#   llm/rag.py               — RAG retrieval (TODO: migrate to TenantSession in Track 2.5)
ALLOWED_FILES="graph/connection.py graph/tenant_session.py graph/schema.py etl/bloodhound.py eti_core/loader.py api/main.py bootstrap.py gnn/embeddings.py gnn/init_gat.py llm/planner.py llm/rag.py"

VIOLATIONS=$(grep -rln "GraphDatabase\.driver(\|driver\.session()" --include="*.py" . \
  | grep -v -E "^\./($( echo "$ALLOWED_FILES" | tr ' ' '|' | sed 's/\./\\./g' ))$" \
  | grep -v "^./migrations/" || true)

if [ -n "$VIOLATIONS" ]; then
  echo "Tenant isolation violation: direct driver access outside approved files:"
  echo "$VIOLATIONS"
  exit 1
fi
echo "OK: no unauthorized direct Neo4j driver access."
