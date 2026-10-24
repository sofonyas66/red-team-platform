# ETHIO-RTAP — Mission Brief for CodeWhale

Deadline: the project is submitted **Sunday 2026-10-25**. Work window: Thu 10-22 evening to Sat 10-24 evening. Sunday is for submitting only.
Place this file at `docs/MISSION.md` and read it fully before any action. It overrides your own plans where they conflict.

"Owner" = the human who runs commands on his machine. You cannot run Docker or pnpm; the owner can. Your reports are never evidence. The owner's script output is.

---

## 1. Goal

Ship a graduation-ready, honest, multi-tenant red team planning platform:

1. Tenant isolation is enforced per **org** and per **engagement** on every graph endpoint, proven by the existing test suite going green.
2. The pipeline works end to end for a **fresh upload**: ingest BloodHound zip -> Node2Vec embeddings -> GAT training -> scored attack paths -> ETI-Core threat actor correlation -> LLM campaign plan.
3. The dashboard shows only real data. No fabricated numbers, no fake "secure" labels.
4. The repo is clean to hand over: no secrets, no dead files, tests runnable with one command.

Everything not on that list is out of scope. Out of scope and NOT to be touched: `rtap` CLI breakage, `config.DATABASE_URL` oddity, `backend/scripts/check_tenant_isolation.sh` (grep-only), the stale `backend`/`frontend` build services in the root `docker-compose.yml`, JWT secret length. They are listed as known limitations in the README by the owner.

---

## 2. Non-negotiable rules

R1. **Never report a result you did not obtain.** If you did not run it, write `not run`. Never write `(no output)` for a command you did not execute. Never describe a diff you did not produce with `git diff`. Never paste a "hunk" from memory. A previous report invented hunks, a no-op diff (identical `-` and `+` lines), and grep results. That is a failure.
R2. **Verification is mechanical.** For every stage you write a script `scripts/verify/<stage>.sh` that prints `PASS: <check>` or `FAIL: <check> (expected X, got Y)` and exits non-zero on any FAIL. Every check prints expected and actual so it cannot pass vacuously. Scripts never print tokens, passwords, or `.env` values. The owner runs the script and replies `PASS` or pastes the FAIL lines only.
R3. **One stage at a time, in order.** Stop at the end of each stage and wait. After the owner says `PASS`, make exactly one commit on the current branch with the message given in the stage. No commit before PASS. No pushing, no merging.
R4. **Three-strike rule.** If a stage's verify fails three times, stop. Write `BLOCKERS.md` (exact failing output, what you tried, your best hypothesis) and move to the next stage that does not depend on it. Do not improvise around a blocker.
R5. **Evidence before edit.** Before editing a file, read the relevant lines and record `file:line` for every claim your change depends on. Line numbers in section 3 come from an earlier audit and may be stale. Re-check them.
R6. **No package installs, no `.env` edits, no DB schema changes, no data deletion.** Never run `docker compose down -v`, `docker volume rm`, `docker system prune`, or any DROP/TRUNCATE/`DETACH DELETE`. numpy and torch are custom-built for a CPU without AVX; never reinstall or upgrade them.
R7. **No mock data, no fabricated UI text.** Do not add placeholder metrics, percentages, or "secure" labels. When data is missing, show an honest empty state.
R8. **Do not break working contracts.** `retrain_gat_background` stays `async def` (a cross-event-loop bug was fixed there once). ML imports stay lazy (no eager torch import at module top-level in `api/main.py`, `llm/planner.py`). Keep every export name that other files import (a previous attempt broke the build with `module-not-found` by renaming hooks).
R9. **Scope fence.** Only touch the files listed under "Allowed files" for the stage. If you need another file, stop and say which and why.
R10. **Owner effort budget.** Each stage costs the owner at most 2 commands. Design for that.

---

## 3. Verified facts (use them, do not re-derive unless a stage says so)

**Repo:** `/home/klythron/Documents/projects/red-team-platform`. Branch `wip/frontend-phase` (local only; the owner merges to master and pushes himself). Python venv: `.venv/` at repo root. Backend in `backend/`, Next.js 16 frontend in `frontend/` (pnpm). There is **no** `lint` script; `pnpm build` is the frontend check.

**Start the stack (owner does this, never you):**
- Databases: `docker compose up -d --no-build neo4j postgres` from the repo root (the root compose `backend`/`frontend` build services are stale and must be skipped). Wait for Postgres (`pg_isready`) and Neo4j (HTTP 7474 = 200). Existing named volumes `red-team-platform_{postgres_data,neo4j_data,neo4j_import,neo4j_logs,qdrant_data}` hold the data; they must keep being reused.
- API, foreground, own terminal: `PYTHONPATH=backend .venv/bin/python backend/start_api.py`. Restart after every backend edit.
- Qdrant is not in the root compose. Stage 3 handles it.

**Accounts and data:** `test-admin@example.com` (org A) owns two engagements already loaded: NORTH (about 290 nodes) and SEVENKINGDOMS (about 294 nodes). `admin2@example.com` is a different org (B). Passwords come only from env vars `RTAP_ADMIN_PW`, `RTAP_ADMIN2_PW` (owner runs `source ~/.rtap-test-env`). Never hardcode ids, emails of other users, or passwords. API base `http://localhost:8000`; `/auth/login` takes JSON `{username,password}` and returns `access_token`; login is rate-limited 5/minute, so scripts log in once per account.

**Tests (already committed in Card 6):** `backend/tests/test_rtap.py`, `backend/tests/conftest.py`. Command: `.venv/bin/python -m pytest backend/tests -q --tb=line -p no:cacheprovider` (add `-m "not llm"` to skip the 4 cases tagged `llm`). Baseline before Stage 1: 13 passed, 8 failed (cross-tenant 404 on three GET endpoints; missing/bad `engagement_id` 422 on `/graph/stats`, `/paths`, `/gnn/status`). After Stage 1 every test must pass, including the `llm` ones, because they stop at 401/404/422 before any LLM call.

**Code facts from the earlier audit (re-verify with file:line before relying on them):**
- `backend/api/main.py`: `/paths` (~333), `/plan/generate` (~352), `/gnn/status` (~374) take `engagement_id` as an unvalidated `str` (`""` default for the first two) and do **no** ownership check. `/graph/stats` Cypher (~216, ~224) filters `org_id` only. The correct pattern already exists in `upload_bloodhound` (~252-261): `engagement_id: uuid.UUID = Form(...)` then `select(Engagement).where(Engagement.id == engagement_id, Engagement.org_id == uuid.UUID(user.org_id))` -> 404.
- `backend/api/main.py` ~313: `upload_bloodhound` schedules `retrain_gat_background(org_id, engagement_id)`; it never calls `run_embeddings` first, so GAT training fails with "No embedded nodes found ... Run gnn/embeddings.py first".
- `backend/gnn/init_gat.py`: `_retrain_status` dict (~40); cache dir keyed `(org_id, engagement_id)` (~47-54); `load_graph_data` Cypher at ~76 and ~89 filters `org_id` only; `initialize_gat` ~270-292.
- `backend/gnn/embeddings.py`: `run_embeddings(org_id, engagement_id)` (~251) is `async def` with CPU-bound PyTorch loops, correctly tenant-scoped.
- `backend/llm/planner.py`: path Cypher (~63-65) has no `engagement_id`; `except Exception: gat_score = 0.5` (~84-88); sort `scored_paths.sort(key=lambda x: x["score"], reverse=True)` raises `TypeError` on `None`; the `ThreatActor`/`Technique` query (~44) is global **by design** (ETI-Core is shared threat intel). Leave it.
- `TenantSession` injects `$org_id` into queries; verify whether it also injects `$engagement_id` (file:line) before using it.
- Neo4j emits harmless warnings that `actor_id`/`technique_id` do not exist because ETI-Core data is currently missing. Stage 3 fixes the cause.

**Past failures (do not repeat):** invented diff hunks; "(no output)" for unrun greps; claiming edits to `page.tsx` that were never made; renaming exports and breaking the build; calling `/paths?engagement_id=` without the required `source` and `target` (backend returns 422); deleting the working "Ingest data" button; leaving `{/* removed */}` comments; skipping the build and reporting success.

---

## 4. Stages

Order: **A -> B -> 1 -> 2 -> 3 -> 4 -> 5**. Stage 4 is optional (cut it if the owner says time is short). Stages A and B come before Stage 1 because Stage 1 makes `engagement_id` mandatory and the dashboard must already send it.

### Stage A — Frontend honesty (page.tsx only)
**Allowed files:** `frontend/app/page.tsx`; `git rm frontend/app/page.tsx.bak` if it is tracked. Do **not** edit `frontend/app/globals.css` (its rules are minified on very long lines; dead CSS is harmless).
**Do:**
1. Remove the sidebar "Protected mode / All systems secure" card (~line 78).
2. Remove the entire "Security posture" panel including the placeholder text and its comment (~197-207).
3. Remove the entire "Collection coverage" section (~348).
4. In "Quick actions" delete **only** the two disabled buttons (Generate plan, Analyze paths). Keep "Ingest data" and its navigation behavior.
5. No replacement comments, no new placeholder text. Delete imports that become unused.
**Verify `scripts/verify/stage-a.sh`:** grep for `Protected mode|Security posture|Collection coverage|68 / 100|svc-backup|Nightfall|84\.6|Not available yet` in `frontend/app/*.tsx frontend/components` (expect zero matches, print actual count); `Ingest data` still present in `page.tsx` (expect >= 1); `page.tsx.bak` absent from `git ls-files`; `cd frontend && pnpm build` exit 0 (print last 5 lines on failure).
**Commit:** `Frontend: remove fabricated dashboard elements`

### Stage B — One shared selected engagement; every data call sends it
**Allowed files:** `frontend/components/topbar.tsx`, `frontend/lib/hooks/*`, `frontend/lib/types/*`, `frontend/app/page.tsx` (wiring only).
**First (read-only, put in the stage report):** `git show HEAD:` the original `frontend/lib/hooks/use-dashboard-data.ts`, `use-graph-stats.ts`, and the topbar. Record with file:line (1) how engagement selection works today (an engagement dropdown and create already exist and work; reuse them, do not build a second one), (2) where `/paths` gets its `source` and `target`, (3) every call to `/graph/stats`, `/paths`, `/gnn/status`.
**Do:**
1. One shared selected-engagement state used by the topbar and all hooks. Fed by `GET /engagements`. Persist only the last-selected id in `localStorage`, validated against the server list on load (drop it if absent). Auto-select when exactly one engagement exists. Empty state when none.
2. Every call to `/graph/stats`, `/paths`, `/gnn/status` sends `engagement_id` and is disabled until one is selected. The dashboard then shows "Select an engagement".
3. `/paths` requires `source` and `target`. Decision rule: if the committed hook already supplied them from some state, keep that exactly. If it did not (the table could never have worked), implement the smallest honest version: two text inputs (source user, target computer) above the table and call `/paths` only on submit. Do not invent a new backend endpoint.
4. Keep every export name and import path that `page.tsx` and other files use.
**Verify `scripts/verify/stage-b.sh`:** `pnpm build` exit 0; every occurrence of `/graph/stats`, `/paths`, `/gnn/status` under `frontend/` is on a line or call that includes `engagement_id` (print any that do not). Then print `OWNER VISUAL CHECK: with the API running, pick NORTH then SEVENKINGDOMS and confirm the stats card changes; with nothing selected confirm 'Select an engagement' shows.`
**Commit:** `Frontend: shared engagement selection; scope data hooks by engagement_id`

### Stage 1 — Backend ownership and validation (security core)
**Allowed files:** `backend/api/main.py` only.
**Do:**
1. Add one shared dependency `require_engagement_ownership(engagement_id: uuid.UUID, user: AuthenticatedUser = Depends(get_current_user)) -> uuid.UUID` that runs the Postgres ownership query (same session style as the existing `/engagements` and `upload_bloodhound` code) and raises `HTTPException(404, "Engagement not found")` when no row matches `Engagement.id == engagement_id AND Engagement.org_id == user.org_id`. Missing or malformed id must yield 422 (typed `uuid.UUID`, no default).
2. Apply `engagement_id: uuid.UUID = Depends(require_engagement_ownership)` to `/graph/stats`, `/paths`, `/gnn/status`, and `/plan/generate`. For `/plan/generate`, `engagement_id` stays a **query** parameter; the body stays `{source,target}`. The 404 must occur **before** any LLM or Neo4j work.
3. Scope the two `/graph/stats` Cypher queries by `engagement_id` as well as `org_id` (after confirming how `TenantSession` supplies `$engagement_id`).
4. Pass `str(engagement_id)` to downstream functions as before.
**Verify `scripts/verify/stage-1.sh`:** run the full test suite without `-m` and require every test to pass (print the pytest summary line; expect `25 passed`); then, using `RTAP_ADMIN_PW`, log in once, list engagements, and print for each of admin1's engagements its name and the node count from `/graph/stats` (expect two different counts, roughly 290 and 294, and neither equal to their sum). Print only names and counts.
**Commit:** `Backend: engagement ownership dependency; scope graph stats by engagement`

### Stage 2 — Embeddings before GAT, off the event loop
**Allowed files:** `backend/gnn/init_gat.py`, `backend/gnn/embeddings.py` (only if a thread boundary requires it), `backend/api/main.py` (only the retrain scheduling line).
**First:** report `file:line` for (a) how `retrain_gat_background` is scheduled, (b) where `_retrain_status` values are set, (c) the exact status strings used, (d) the ingestion dedupe key in `backend/db/ingestion_ops.py` (the verify script uploads a sample zip into a fresh engagement and a duplicate-hash 409 would break it; handle that case in the script).
**Do:**
1. Add `AND n.engagement_id = $engagement_id` to the `load_graph_data` node query (~76) and `a.engagement_id = $engagement_id AND b.engagement_id = $engagement_id` to the relationship query (~89).
2. In `retrain_gat_background` (still `async def`): set status to an in-progress value, `await run_embeddings(org_id, engagement_id)`, then `initialize_gat(...)`. Only CPU-bound torch work may go through `asyncio.to_thread`; no Neo4j async calls inside the thread.
3. Any exception in embeddings or training sets the status to the failure value with the error message and does **not** propagate to crash the process.
**Verify `scripts/verify/stage-2.sh`** (needs env `SAMPLE_ZIP` = path to a BloodHound zip, e.g. the SEVENKINGDOMS sample): create a fresh engagement via `POST /engagements`; upload the zip; poll `/gnn/status` every 5 s up to 15 min and print elapsed time; require status `ready`; call `/paths` for `RENLY.BARATHEON@SEVENKINGDOMS.LOCAL` -> `KINGSLANDING.SEVENKINGDOMS.LOCAL` on that engagement and require a numeric, non-null `score` (do not require a specific value); then a failure check: run `PYTHONPATH=backend .venv/bin/python` calling `retrain_gat_background` on an engagement with no nodes and require that it returns without raising and that `get_retrain_status` reports the failure value; finally `GET /health` returns 200.
**Commit:** `GNN: run tenant-scoped embeddings before GAT retrain; scope graph loading by engagement`

### Stage 3 — Seed ETI-Core threat intelligence
**Allowed files:** none (execution only; at most a new `scripts/verify/stage-3.sh`).
**Do:**
1. Read-only first: write a Python snippet (`.venv/bin/python`) printing Neo4j counts of `ThreatActor`, `Technique`, `Sector` and the Qdrant `eti_core` collection point count. Qdrant is not in the root compose. Check `.env` variable **names** (never values) and `docker ps -a` to find how Qdrant was started; its data volume `red-team-platform_qdrant_data` already exists. Give the owner one exact command to start it **reusing that volume** (default image `qdrant/qdrant`, port 6333, storage mount `/qdrant/storage`) and confirm against the `.env` Qdrant URL.
2. If counts are zero, the owner runs `PYTHONPATH=backend .venv/bin/python backend/eti_core/loader.py` (idempotent `MERGE`, confirm with file:line) then `backend/llm/rag.py` (confirm it has a `__main__` and upserts with deterministic ids so re-runs do not duplicate points). If counts are already non-zero, close the stage with the counts as evidence.
**Verify `scripts/verify/stage-3.sh`:** print before/after counts; require `ThreatActor > 0`, `Technique > 0`, Qdrant points `> 0`; log in and require `GET /actors` returns a non-empty list (print the first item's keys, not secrets).
**Commit (if anything changed in the repo):** `ETI-Core: add seed verification script`

### Stage 4 — OPTIONAL (only if time): honest unscored paths
Do not start unless the owner says so. Pairs a backend change with a frontend change; both or neither.
**Allowed files:** `backend/llm/planner.py`, `frontend/app/page.tsx` and the score type file.
**First:** `file:line` of what `score_candidate_path` does when no model exists (raise, or return a default). Also run in Neo4j: `MATCH ()-[r]->() RETURN count(r), count(r.engagement_id)`; if not equal, relationships lack the property and the Cypher must not filter on `r.*`.
**Do:** scope the path Cypher with `ALL(x IN nodes(p) WHERE x.org_id = $org_id AND x.engagement_id = $engagement_id)` (and `src`/`dst`); replace `gat_score = 0.5` with `None` and log the swallowed exception with `logger.warning`; make the sort None-safe (None last); fix the `:.4f` prompt formatting for None; the dashboard renders `Not scored` for null and the score type becomes `number | null`. Do not touch planner line ~44.
**Verify:** `/paths` on an engagement without a trained model returns `"score": null` (not `0.5`); the same source user queried in NORTH and SEVENKINGDOMS returns only nodes of the queried engagement; `pnpm build` exit 0.
**Commit:** `Planner: return null score when unscored; scope path query by engagement; UI shows Not scored`

### Stage 5 — Repo hygiene (no README; the owner writes it)
**Allowed files:** `.gitignore`, `.env.example`, removal of dead tracked files.
**Do:** confirm `.env` and `backend/.env` are untracked and ignored; create `.env.example` with variable **names only** (no values); list tracked files that look like leftovers (`*.bak`, scratch notes) and propose deletions without deleting; confirm `ethio-rtap-status.md` stays untracked.
**Verify `scripts/verify/stage-5.sh`:** `git ls-files | grep -E '(^|/)\.env$'` prints nothing; `git grep -n -I -E 'AIza|sk-[A-Za-z0-9]{10,}|BEGIN (RSA|PRIVATE)'` prints nothing; `.env.example` exists and contains no `=` followed by a non-empty value; `git status --short` is empty.
**Commit:** `Repo hygiene: env example, ignore rules`

---

## 4b. Use sub-agents (required for every stage)

You are the **orchestrator**. Keep your own context small by delegating. Use three roles per stage:

1. **Evidence sub-agents (read-only, run in parallel).** At the start of a stage, spawn read-only sub-agents to collect the `file:line` facts the stage needs (for example: how `/engagements` opens its DB session, whether `TenantSession` injects `$engagement_id`, how the original frontend hook got `source`/`target`). Each gets one narrow question and returns only `file:line` plus the exact quoted line. Independent questions run in parallel in a single step.
2. **Implementer sub-agent (one at a time per stage).** Give it only: the stage section, rules R1-R10, the evidence from step 1, and the allowed-files list. It edits those files and writes `scripts/verify/<stage>.sh`. Never run two implementers that can touch the same file. Obey stage order: Stage 1 must not start before Stage B has PASS and is committed.
3. **Reviewer sub-agent (read-only, a different agent from the implementer).** After the implementer finishes, the reviewer reads `git diff` and the verify script and answers only: (a) does every changed file appear in the allowed list, (b) does any change violate R6-R8 (installs, `.env`, `async def`, lazy imports, renamed exports), (c) can any verify check pass vacuously (it does not print expected and actual, or tests the wrong thing), (d) is any claim in the draft stage report not backed by real command output. It returns concrete defects or the word `CLEAN`. Fix defects before asking the owner to run anything.

Rules for sub-agents:
- A sub-agent's message is not evidence either (R1 applies). Confirm its claims yourself with a real read-only command (`git diff`, `grep -n`, `sed -n`) before including them in a report.
- Sub-agents never run Docker, never touch the network, never commit, never push.
- Pass each sub-agent only what it needs, not this whole file.
- Record in the stage report which sub-agents ran and for what, one line each.

## 5. Stage report format (print this and nothing else when a stage's code is ready)

1. `git status --short` (real output)
2. `git diff --stat` (real output)
3. `file:line` evidence list for the claims the stage depended on
4. The single command the owner runs: `source ~/.rtap-test-env && bash scripts/verify/<stage>.sh`
5. The line: `Status: awaiting owner run. Results: not run.`

Do not summarize what the code "should" do instead of showing evidence. Do not paste entire files. Wait for `PASS` or FAIL lines.

## 6. Definition of done for the whole mission

- Stages A, B, 1, 2, 3, 5 each have a PASS and a commit (Stage 4 optional).
- `pytest backend/tests` fully green; `pnpm build` exit 0; row counts of `engagements` and `ingestion_records` unchanged by tests.
- A fresh upload yields a scored path with no manual embedding step.
- `BLOCKERS.md` exists only if a stage was blocked, and lists each blocker precisely.
