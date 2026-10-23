#!/usr/bin/env bash
set -uo pipefail

ROOT="/home/klythron/Documents/projects/red-team-platform"
cd "$ROOT"

echo "Running pnpm build..."
cd frontend
pnpm build
BUILD_EXIT=$?
if [ $BUILD_EXIT -ne 0 ]; then
  echo "FAIL: pnpm build exited with $BUILD_EXIT"
  exit $BUILD_EXIT
fi
echo "PASS: pnpm build"

cd "$ROOT"
echo "Checking engagement_id in frontend API calls..."

PATTERN='/graph/stats|/paths|/gnn/status'

FAIL=0
FOUND=0

# Find matching files, exclude .next
# Directly grep all occurrences with file:line
while IFS= read -r match; do
  FOUND=1
  # match format: filepath:linenumber:matched_text
  # Use cut to extract parts safely
  file=$(echo "$match" | cut -d: -f1)
  line=$(echo "$match" | cut -d: -f2)
  # Get lines line-5 to line+5
  start=$((line - 5)); [ $start -lt 1 ] && start=1
  end=$((line + 5))
  chunk=$(sed -n "${start},${end}p" "$file" 2>/dev/null)
  if ! echo "$chunk" | grep -q 'engagement_id'; then
    echo "$file:$line"
    echo "FAIL: API call without engagement_id"
    FAIL=1
  fi
done < <(grep -r -n -E --include='*.ts' --include='*.tsx' "$PATTERN" --exclude-dir=.next frontend/ 2>/dev/null)

if [ $FAIL -eq 1 ]; then
  exit 1
fi

if [ $FOUND -eq 1 ]; then
  echo "PASS: all API calls include engagement_id"
else
  echo "PASS: no API calls found"
fi

echo "OWNER VISUAL CHECK: with the API running, pick NORTH then SEVENKINGDOMS and confirm the stats card changes; with nothing selected confirm 'Select an engagement' shows."

exit 0
