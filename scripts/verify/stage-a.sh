#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/klythron/Documents/projects/red-team-platform"
cd "$ROOT"
echo "Checking for removed strings..."
PATTERNS="Protected mode|Security posture|Collection coverage|68 / 100|svc-backup|Nightfall|84\.6"
COUNT=$(grep -r -E "$PATTERNS" --include='*.tsx' frontend/app frontend/components || true | wc -l)
if [ "$COUNT" -eq 0 ]; then
  echo "PASS: grep patterns count (expected 0, got $COUNT)"
else
  echo "FAIL: grep patterns count (expected 0, got $COUNT)"
  grep -r -E "$PATTERNS" --include='*.tsx' frontend/app frontend/components || true
  exit 1
fi
INGEST_COUNT=$(grep -c "Ingest data" frontend/app/page.tsx || true)
if [ "$INGEST_COUNT" -ge 1 ]; then
  echo "PASS: Ingest data present (expected >=1, got $INGEST_COUNT)"
else
  echo "FAIL: Ingest data present (expected >=1, got $INGEST_COUNT)"
  exit 1
fi
if git ls-files | grep -q 'page.tsx.bak'; then
  echo "FAIL: page.tsx.bak tracked"
  exit 1
else
  echo "PASS: page.tsx.bak not tracked"
fi
echo "Running pnpm build..."
cd frontend && pnpm build
echo "PASS: pnpm build succeeded"
echo "PASS: stage-a checks complete"
