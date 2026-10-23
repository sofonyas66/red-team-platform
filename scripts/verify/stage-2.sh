#!/usr/bin/env bash
# scripts/verify/stage-2.sh — Verify Stage 2: Embeddings before GAT, off the event loop
# Requirements:
#   - SAMPLE_ZIP must be exported in env (owner sets this)
#   - Reports dedupe key first
#   - Creates fresh engagement, uploads zip with hash-dedup handling
#   - Polls /gnn/status with timeout, prints elapsed time
#   - Calls /paths with known source/target, asserts numeric non-null score
#   - Prints PASS/FAIL with evidence

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${YELLOW}[stage-2]${NC} $*"; }
pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

# ── Config ──────────────────────────────────────────────────────────────────
API_BASE="${API_BASE:-http://localhost:8000}"
SAMPLE_ZIP="${SAMPLE_ZIP:-/home/klythron/Documents/projects/red-team-platform-files/Bloodhound-CE-Sample-Data/SEVENKINGDOMS.zip}"
EMAIL="${RTAP_ADMIN_EMAIL:-test-admin@example.com}"
PASSWORD="${RTAP_ADMIN_PW}"
SOURCE_NODE="${SOURCE_NODE:-RENLY.BARATHEON@SEVENKINGDOMS.LOCAL}"
TARGET_NODE="${TARGET_NODE:-KINGSLANDING.SEVENKINGDOMS.LOCAL}"
MAX_POLL_SECONDS=1500
POLL_INTERVAL=5

if [[ -z "${PASSWORD}" ]]; then
    fail "RTAP_ADMIN_PW not set"
fi
if [[ ! -f "${SAMPLE_ZIP}" ]]; then
    fail "SAMPLE_ZIP not found: ${SAMPLE_ZIP}"
fi

# ── 1. Report dedupe key ────────────────────────────────────────────────────
log "Dedupe key location:"
grep -n "is_already_ingested" backend/db/ingestion_ops.py | head -1
echo

# ── 2. Login ────────────────────────────────────────────────────────────────
log "Authenticating..."
TOKEN=$(curl -s -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" | jq -r '.access_token')
if [[ -z "${TOKEN}" || "${TOKEN}" == "null" ]]; then
    fail "Login failed"
fi
pass "Login OK"

# ── 3. Create fresh engagement ──────────────────────────────────────────────
ENG_NAME="stage2-verify-$(date +%s)"
log "Creating engagement: ${ENG_NAME}"
ENG_RESPONSE=$(curl -s -X POST "${API_BASE}/engagements" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${ENG_NAME}\"}")
ENG_ID=$(echo "${ENG_RESPONSE}" | jq -r '.id')
if [[ -z "${ENG_ID}" || "${ENG_ID}" == "null" ]]; then
    fail "Engagement creation failed: ${ENG_RESPONSE}"
fi
pass "Created engagement: ${ENG_ID}"

# ── 4. Prepare modified zip (hash-dedup handling) ───────────────────────────
log "Preparing modified zip..."
WORK_DIR=$(mktemp -d)
trap "rm -rf ${WORK_DIR}" EXIT
cd "${WORK_DIR}"
unzip -q "${SAMPLE_ZIP}"
echo '{"dummy": "test"}' > dummy.json
MODIFIED_ZIP="${WORK_DIR}/modified.zip"
zip -qr "${MODIFIED_ZIP}" .
pass "Modified zip ready: ${MODIFIED_ZIP}"

# ── 5. Upload zip (triggers background retrain) ─────────────────────────────
log "Uploading zip..."
UPLOAD_RESPONSE=$(curl -s -X POST "${API_BASE}/ingest/bloodhound" \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "file=@${MODIFIED_ZIP};type=application/zip" \
    -F "engagement_id=${ENG_ID}")
UPLOAD_STATUS=$(echo "${UPLOAD_RESPONSE}" | jq -r '.status // "error"')
if [[ "${UPLOAD_STATUS}" != "success" ]]; then
    fail "Upload failed: ${UPLOAD_RESPONSE}"
fi
pass "Upload successful"

# ── 6. Poll /gnn/status with timeout ────────────────────────────────────────
log "Polling /gnn/status (timeout ${MAX_POLL_SECONDS}s)..."
START_TIME=$(date +%s)
ELAPSED=0
for (( i=0; i<MAX_POLL_SECONDS/POLL_INTERVAL; i++ )); do
    GNN_RESPONSE=$(curl -s -G "${API_BASE}/gnn/status" \
        -H "Authorization: Bearer ${TOKEN}" \
        --data-urlencode "engagement_id=${ENG_ID}")
    STATUS=$(echo "${GNN_RESPONSE}" | jq -r '.status // "unknown"')
    ELAPSED=$(($(date +%s) - START_TIME))
    log "  [${ELAPSED}s] status=${STATUS}"
    if [[ "${STATUS}" == "ready" ]]; then
        pass "GNN status ready after ${ELAPSED}s"
        break
    elif [[ "${STATUS}" == "failed" ]]; then
        ERROR=$(echo "${GNN_RESPONSE}" | jq -r '.error // "unknown error"')
        fail "GNN retraining failed: ${ERROR}"
    fi
    sleep "${POLL_INTERVAL}"
done
if [[ "${STATUS}" != "ready" ]]; then
    fail "Timeout after ${MAX_POLL_SECONDS}s waiting for GNN ready (last status: ${STATUS})"
fi

# ── 7. Call /paths and assert numeric non-null score ────────────────────────
log "Querying /paths..."
PATHS_RESPONSE=$(curl -s -G "${API_BASE}/paths" \
    -H "Authorization: Bearer ${TOKEN}" \
    --data-urlencode "source=${SOURCE_NODE}" \
    --data-urlencode "target=${TARGET_NODE}" \
    --data-urlencode "engagement_id=${ENG_ID}")

PATH_COUNT=$(echo "${PATHS_RESPONSE}" | jq 'length')
if [[ "${PATH_COUNT}" -eq 0 ]]; then
    fail "No paths returned"
fi

# Check that at least one path has a numeric non-null score != 0.5 (fallback)
HAS_NUMERIC_SCORE=$(echo "${PATHS_RESPONSE}" | jq '[.[] | select(.score != null and (.score | type == "number") and .score != 0.5)] | length > 0')
if [[ "${HAS_NUMERIC_SCORE}" != "true" ]]; then
    fail "No numeric non-null score found (or all scores are 0.5 fallback): ${PATHS_RESPONSE}"
fi

# Show first few scores
FIRST_SCORES=$(echo "${PATHS_RESPONSE}" | jq '[.[] | .score] | .[0:3]')
pass "/paths returned numeric scores: ${FIRST_SCORES}"

echo
# ── 8. Failure path check (empty engagement) ────────────────────────────────
log "Testing failure path on empty engagement..."
EMPTY_ENG_NAME="stage2-empty-$(date +%s)"
EMPTY_ENG_RESPONSE=$(curl -s -X POST "${API_BASE}/engagements" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${EMPTY_ENG_NAME}\"}")
EMPTY_ENG_ID=$(echo "${EMPTY_ENG_RESPONSE}" | jq -r '.id')
if [[ -z "${EMPTY_ENG_ID}" || "${EMPTY_ENG_ID}" == "null" ]]; then
    fail "Empty engagement creation failed: ${EMPTY_ENG_RESPONSE}"
fi
pass "Created empty engagement: ${EMPTY_ENG_ID}"

# Get org_id from /gnn/status
ORG_ID=$(curl -s -G "${API_BASE}/gnn/status" \
    -H "Authorization: Bearer ${TOKEN}" \
    --data-urlencode "engagement_id=${EMPTY_ENG_ID}" | jq -r '.org_id')
if [[ -z "${ORG_ID}" || "${ORG_ID}" == "null" ]]; then
    fail "Could not get org_id from /gnn/status"
fi
log "Org ID: ${ORG_ID}"

# Call retrain_gat_background directly via Python (no API endpoint)
log "Calling retrain_gat_background on empty engagement via Python..."
EMPTY_START=$(date +%s)
PYTHON_OUTPUT=$(PYTHONPATH=backend /home/klythron/Documents/projects/red-team-platform/.venv/bin/python -c "
import asyncio
import sys
sys.path.insert(0, 'backend')
from gnn.init_gat import retrain_gat_background, get_retrain_status

async def test():
    org_id = '${ORG_ID}'
    engagement_id = '${EMPTY_ENG_ID}'
    try:
        await retrain_gat_background(org_id, engagement_id)
        print('retrain_gat_background returned without raising')
    except Exception as e:
        print(f'retrain_gat_background raised: {e}')
    status = get_retrain_status(org_id, engagement_id)
    print(f'status={status}')

asyncio.run(test())
")
EMPTY_ELAPSED=$(( $(date +%s) - EMPTY_START ))
log "Empty engagement retrain completed in ${EMPTY_ELAPSED}s"
echo "${PYTHON_OUTPUT}"

# Extract status from Python output
EMPTY_STATUS=$(echo "${PYTHON_OUTPUT}" | grep '^status=' | sed 's/^status=//')
if echo "${EMPTY_STATUS}" | grep -q "'status': 'failed'"; then
    pass "Empty engagement retrain failed as expected: ${EMPTY_STATUS}"
else
    fail "Empty engagement retrain did not report failed status: ${EMPTY_STATUS}"
fi

# ── 9. Final GET /health = 200 ──────────────────────────────────────────────
log "Final GET /health check..."
HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/health")
if [[ "${HEALTH_CODE}" != "200" ]]; then
    fail "GET /health returned ${HEALTH_CODE}, expected 200"
fi
pass "GET /health = 200"

# ── 10. Concurrency check: during retrain, GET /health and GET /graph/stats every 2s ────────
log "Concurrency check: starting new retrain and polling /health + /graph/stats every 2s..."
CONC_ENG_NAME="stage2-conc-$(date +%s)"
CONC_ENG_RESPONSE=$(curl -s -X POST "${API_BASE}/engagements" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${CONC_ENG_NAME}\"}")
CONC_ENG_ID=$(echo "${CONC_ENG_RESPONSE}" | jq -r '.id')
if [[ -z "${CONC_ENG_ID}" || "${CONC_ENG_ID}" == "null" ]]; then
    fail "Concurrency engagement creation failed: ${CONC_ENG_RESPONSE}"
fi
pass "Created concurrency engagement: ${CONC_ENG_ID}"

# Upload to trigger retrain
CONC_WORK_DIR=$(mktemp -d)
cd "${CONC_WORK_DIR}"
unzip -q "${SAMPLE_ZIP}"
echo '{"dummy": "concurrency"}' > dummy_conc.json
CONC_ZIP="${CONC_WORK_DIR}/conc.zip"
zip -qr "${CONC_ZIP}" .

curl -s -X POST "${API_BASE}/ingest/bloodhound" \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "file=@${CONC_ZIP};type=application/zip" \
    -F "engagement_id=${CONC_ENG_ID}" > /dev/null
log "Concurrency upload triggered, polling /health and /graph/stats..."

CONC_START=$(date +%s)
HEALTH_200_COUNT=0
STATS_200_COUNT=0
TOTAL_POLLS=0
while true; do
    # Check /health
    HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/health")
    if [[ "${HEALTH_CODE}" == "200" ]]; then
        ((HEALTH_200_COUNT++))
    else
        fail "/health returned ${HEALTH_CODE} during retrain"
    fi

    # Check /graph/stats
    STATS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -G "${API_BASE}/graph/stats" \
        -H "Authorization: Bearer ${TOKEN}" \
        --data-urlencode "engagement_id=${CONC_ENG_ID}")
    if [[ "${STATS_CODE}" == "200" ]]; then
        ((STATS_200_COUNT++))
    else
        fail "/graph/stats returned ${STATS_CODE} during retrain"
    fi

    ((TOTAL_POLLS++))

    # Check if retrain is done
    CONC_STATUS_RESPONSE=$(curl -s -G "${API_BASE}/gnn/status" \
        -H "Authorization: Bearer ${TOKEN}" \
        --data-urlencode "engagement_id=${CONC_ENG_ID}")
    CONC_STATUS=$(echo "${CONC_STATUS_RESPONSE}" | jq -r '.status // "unknown"')
    if [[ "${CONC_STATUS}" == "ready" || "${CONC_STATUS}" == "failed" ]]; then
        CONC_ELAPSED=$(( $(date +%s) - CONC_START ))
        log "Retrain ${CONC_STATUS} after ${CONC_ELAPSED}s, stopping concurrency polls"
        break
    fi

    sleep 2
done

pass "Concurrency check passed: ${TOTAL_POLLS} polls, /health 200=${HEALTH_200_COUNT}, /graph/stats 200=${STATS_200_COUNT}"

# Cleanup
cd /
rm -rf "${CONC_WORK_DIR}"

echo
pass "Stage 2 verification complete"
echo "  Engagement: ${ENG_ID}"
echo "  GNN ready after ${ELAPSED}s"
echo "  Paths found: ${PATH_COUNT}"
echo "  Scores are numeric and not the 0.5 fallback"
echo "  Empty engagement failure status: ${EMPTY_STATUS}"
echo "  Final /health: 200"
echo "  Concurrency polls: ${TOTAL_POLLS} (all 200)"