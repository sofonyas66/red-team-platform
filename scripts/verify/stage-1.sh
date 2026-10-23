#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 1 Verification ==="
echo "1. Backend import check..."
PYTHONPATH=backend .venv/bin/python -c "import api.main" && echo "IMPORT OK"

echo "2. Pyflakes (no undefined names)..."
.venv/bin/python -m pyflakes backend/api/main.py 2>&1 | grep -v "imported but unused" || true

echo "3. Check dependency exists in code..."
grep -n "require_engagement_ownership" backend/api/main.py | head -5

echo "4. Check it's applied to /graph/stats..."
grep -A20 '@app.get("/graph/stats")' backend/api/main.py | grep "require_engagement_ownership" && echo "FOUND" || echo "NOT FOUND"

echo "5. Check it's applied to /paths..."
grep -A20 '@app.get("/paths")' backend/api/main.py | grep "require_engagement_ownership" && echo "FOUND" || echo "NOT FOUND"

echo "6. Check it's applied to /plan/generate..."
grep -A20 '@app.post("/plan/generate")' backend/api/main.py | grep "require_engagement_ownership" && echo "FOUND" || echo "NOT FOUND"

echo "7. Check it's applied to /gnn/status..."
grep -A20 '@app.get("/gnn/status")' backend/api/main.py | grep "require_engagement_ownership" && echo "FOUND" || echo "NOT FOUND"

echo "8. Check Cypher queries scope by engagement_id in /graph/stats..."
grep -A30 "async def graph_stats" backend/api/main.py | grep -E "engagement_id"

echo "=== Stage 1 static checks complete ==="
echo "Run full test suite with API running: PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_rtap.py -v"