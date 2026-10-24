#!/usr/bin/env bash
set -euo pipefail

echo "=== Stage 4a Verification: Engagement scoping of /paths query ==="

# Load env
source ~/.rtap-test-env

NORTH_NAME="${NORTH_NAME:-north-test}"
SEVEN_NAME="${SEVEN_NAME:-sevenkingdoms-test}"
SOURCE="RENLY.BARATHEON@SEVENKINGDOMS.LOCAL"
TARGET="KINGSLANDING.SEVENKINGDOMS.LOCAL"

# Login once
echo "Logging in..."
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"test-admin@example.com\",\"password\":\"$RTAP_ADMIN_PW\"}" | jq -r .access_token)

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "FAIL: Could not obtain token"
  exit 1
fi
echo "PASS: Got token"

# Find engagement IDs
echo "Finding engagement IDs..."
ENGAGEMENTS=$(curl -s -G "http://localhost:8000/engagements" -H "Authorization: Bearer $TOKEN")
NORTH_ID=$(echo "$ENGAGEMENTS" | jq -r ".[] | select(.name == \"$NORTH_NAME\") | .id")
SEVEN_ID=$(echo "$ENGAGEMENTS" | jq -r ".[] | select(.name == \"$SEVEN_NAME\") | .id")

if [[ -z "$NORTH_ID" || "$NORTH_ID" == "null" ]]; then
  echo "FAIL: Could not find engagement '$NORTH_NAME'"
  exit 1
fi
if [[ -z "$SEVEN_ID" || "$SEVEN_ID" == "null" ]]; then
  echo "FAIL: Could not find engagement '$SEVEN_NAME'"
  exit 1
fi
echo "PASS: Found $NORTH_NAME = $NORTH_ID"
echo "PASS: Found $SEVEN_NAME = $SEVEN_ID"

# Test /paths on NORTH (expect 0 paths)
echo ""
echo "Testing /paths on $NORTH_NAME (expect 0 paths)..."
NORTH_PATHS=$(curl -s -G "http://localhost:8000/paths" \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "source=$SOURCE" \
  --data-urlencode "target=$TARGET" \
  --data-urlencode "engagement_id=$NORTH_ID")

NORTH_COUNT=$(echo "$NORTH_PATHS" | jq 'length')
echo "Response: $NORTH_PATHS"
echo "Path count: $NORTH_COUNT"

if [[ "$NORTH_COUNT" -eq 0 ]]; then
  echo "PASS: north-test returned 0 paths (expected 0)"
else
  echo "FAIL: north-test returned $NORTH_COUNT paths (expected 0)"
  exit 1
fi

# Test /paths on SEVEN (expect > 0 paths)
echo ""
echo "Testing /paths on $SEVEN_NAME (expect > 0 paths)..."
SEVEN_PATHS=$(curl -s -G "http://localhost:8000/paths" \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "source=$SOURCE" \
  --data-urlencode "target=$TARGET" \
  --data-urlencode "engagement_id=$SEVEN_ID")

SEVEN_COUNT=$(echo "$SEVEN_PATHS" | jq 'length')
echo "Response: $SEVEN_PATHS"
echo "Path count: $SEVEN_COUNT"

if [[ "$SEVEN_COUNT" -gt 0 ]]; then
  echo "PASS: sevenkingdoms-test returned $SEVEN_COUNT paths (expected > 0)"
else
  echo "FAIL: sevenkingdoms-test returned $SEVEN_COUNT paths (expected > 0)"
  exit 1
fi

# Run full pytest suite
echo ""
echo "Running full pytest suite..."
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests/test_rtap.py -v --tb=short 2>&1 | tail -30

PYTEST_EXIT=${PIPESTATUS[0]}
if [[ "$PYTEST_EXIT" -eq 0 ]]; then
  echo "PASS: pytest suite passed (25 tests)"
else
  echo "FAIL: pytest suite failed with exit code $PYTEST_EXIT"
  exit 1
fi

echo ""
echo "=== ALL STAGE 4a CHECKS PASSED ==="