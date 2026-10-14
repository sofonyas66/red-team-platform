---

## Phase 2 Verification Plan — Reliability & Per-Tenant GNN Caching

**Goal:** Confirm `phase2-reliability-gnn-caching.md` is not just implemented but actually correct under real conditions. Every item below needs real terminal output, not a status claim.

### Step 0 — Locate the implementation
Before testing anything, have the agent find and report (with file:line) where:
- The GNN model/embedding cache is stored (in-memory dict, Redis, disk, or Neo4j-backed) and what key it's cached under
- `retrain_gat_background` (or equivalent) lives, and confirm it's still `async def` (not a sync wrapper calling `asyncio.run()` — this was already fixed once per your notes, so this is a regression check)

### Step 1 — Single-tenant correctness
- Trigger a GNN retrain/cache-populate for tenant A only
- Confirm cache is populated and a cache-hit path returns the same result as a fresh computation (no silent staleness)

### Step 2 — Cross-tenant cache isolation
- Populate the cache for tenant A, then request a prediction/score for tenant B
- Confirm tenant B does NOT get tenant A's cached result (this is the actual bug class to watch for — a cache keyed only by model type rather than `org_id`/`engagement_id` would leak across tenants exactly like the embeddings bug did)
- Real evidence: print/log the cache key used for each request, for both tenants, side by side

### Step 3 — Concurrent access (the "reliability" half of Phase 2)
- Fire retrain/caching requests for tenant A and tenant B at the same time (e.g. two concurrent `asyncio.gather()` calls or two parallel API requests)
- Confirm neither request blocks the other (background task is genuinely async — check wall-clock time: concurrent should take ~max(A,B), not sum(A,B))
- Confirm no cross-contamination of results after concurrent completion (re-check Step 2's isolation under concurrency, not just sequentially)

### Step 4 — Cache invalidation
- Re-ingest new data for tenant A (simulating a new SharpHound export)
- Confirm the cache correctly invalidates/refreshes for tenant A and does NOT force an unnecessary invalidation for tenant B

### Required evidence per step
- Real terminal/log output showing the actual cache key, actual timing, actual result values compared across tenants
- Not acceptable: a table of ✅ marks with no output backing it (same rule as the embeddings fix)

---
