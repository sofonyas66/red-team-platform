# ETHIO-RTAP — gnn/embeddings.py: Tenant Scoping & Async Migration

> **Audience:** Coding agent implementing against this spec.
> **Verification requirement:** Same standard as every other phase today — real terminal output required. In particular, this fix MUST be proven with a real two-tenant test showing embeddings written for one tenant do NOT appear on another tenant's nodes, even when those nodes share the same `objectid` (this is a genuine, confirmed-possible collision in this system — not a hypothetical).

---

## Problem (confirmed via direct code review, not yet run)

`gnn/embeddings.py` was written before multi-tenant isolation existed in this codebase and has never been updated. Three real issues:

1. **`fetch_graph_from_neo4j()`** queries `MATCH (n) RETURN ...` and `MATCH (s)-[r]->(t) RETURN ...` with no `org_id` filter at all — it pulls every node and relationship from every tenant into one combined graph.

2. **`run_node2vec()`** would then train a single Node2Vec model on this combined, unscoped graph — meaning one tenant's embeddings would be shaped by another tenant's AD structure. This directly violates the per-tenant isolation design established earlier today (GAT models must never be shared or cross-influenced between tenants).

3. **`store_embeddings_in_neo4j()`** writes back with `MATCH (n) WHERE n.objectid = item.objectid OR n.actor_id = item.objectid OR n.name = item.objectid` — again no `org_id` filter. This is worse than #1 and #2: because sample/test data can produce identical `objectid` values across different tenants (confirmed today — the same SharpHound sample zip was ingested under multiple different `org_id`s during testing), this write pattern can silently overwrite one tenant's node with an embedding computed from a completely different tenant's graph. This is a real cross-tenant data integrity bug, not just a training-quality concern.

Additionally, the file uses the old sync `with driver.session()` pattern throughout, inconsistent with the async migration completed earlier in this phase.

## Fix

### 1. `fetch_graph_from_neo4j(org_id: str, engagement_id: str)`
Add required `org_id`/`engagement_id` parameters. Scope both queries:

```python
async def fetch_graph_from_neo4j(org_id: str, engagement_id: str):
    G = nx.Graph()
    node_to_idx = {}
    idx_to_node = {}

    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        nodes_result = await ts.run("""
            MATCH (n)
            WHERE n.org_id = $org_id AND n.engagement_id = $engagement_id
            RETURN
                CASE
                    WHEN n.objectid IS NOT NULL THEN n.objectid
                    WHEN n.actor_id IS NOT NULL THEN n.actor_id
                    WHEN n.technique_id IS NOT NULL THEN n.technique_id
                    ELSE n.name
                END AS objectid,
                labels(n) AS labels,
                n.name AS name
        """)
        node_count = 0
        async for record in nodes_result:
            ...  # unchanged logic

        rels_result = await ts.run("""
            MATCH (s)-[r]->(t)
            WHERE s.org_id = $org_id AND s.engagement_id = $engagement_id
              AND t.org_id = $org_id AND t.engagement_id = $engagement_id
            RETURN
                CASE WHEN s.objectid IS NOT NULL THEN s.objectid ... END AS source,
                CASE WHEN t.objectid IS NOT NULL THEN t.objectid ... END AS target,
                type(r) AS rel_type
        """)
        async for record in rels_result:
            ...  # unchanged logic

    return G, node_to_idx, idx_to_node
```

Note: `TenantSession.run()` already auto-injects `org_id`/`engagement_id` into query params per its existing implementation — confirm the query strings above reference `$org_id`/`$engagement_id` so the isolation-check heuristic in `TenantSession` doesn't warn/fail (it checks that the literal string `org_id` appears in the query).

### 2. `store_embeddings_in_neo4j(embeddings, idx_to_node, org_id: str, engagement_id: str, dimensions=128)`
This is the critical fix. Add `org_id`/`engagement_id` to the write-back MATCH:

```python
async def store_embeddings_in_neo4j(embeddings, idx_to_node, org_id: str, engagement_id: str, dimensions=128):
    batch = [...]  # unchanged

    async with TenantSession(org_id=org_id, engagement_id=engagement_id) as ts:
        batch_size = 500
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            query = """
            UNWIND $batch AS item
            MATCH (n)
            WHERE
                (n.objectid = item.objectid
                 OR n.actor_id = item.objectid
                 OR n.technique_id = item.objectid
                 OR n.name = item.objectid)
                AND n.org_id = $org_id
                AND n.engagement_id = $engagement_id
            SET n.embedding = item.embedding,
                n.embedding_dim = $dimensions
            """
            await ts.run(query, batch=chunk, dimensions=dimensions)
```

This is the line that prevents the cross-tenant overwrite bug described above — every write is now scoped to the specific tenant+engagement, so an `objectid` collision across tenants can no longer cause a cross-tenant write.

### 3. `run_node2vec()`
No tenant-scoping change needed here — it operates on the `Data` object already built from tenant-scoped fetch results, so it's implicitly scoped correctly once §1 is fixed. Keep as `def` (not async) — this is pure CPU/GPU compute, no I/O, no reason to make it a coroutine. It's fine for the calling code to run this synchronously inside an otherwise-async pipeline (it will block the event loop during training, which is expected and acceptable if called from `initialize_gat`'s background-task context — same as the existing GAT training call pattern).

### 4. Top-level `main()` / script entrypoint
Update whatever currently runs when the file is executed as a script (`if __name__ == "__main__":` block, not shown in what's been reviewed so far — check for it) to require `org_id` and `engagement_id` as CLI arguments (e.g. via `argparse` or `typer`, matching the project's existing CLI conventions) rather than running unscoped. Running this script with no tenant scope specified should be a hard error, not a default-to-everything behavior.

### 5. Wire into `initialize_gat()` / `gnn/init_gat.py`
Per the error message already surfacing in testing today ("No embedded nodes found... Run gnn/embeddings.py first."), GAT training currently expects embeddings to already exist but has no automated way to trigger their generation. Two options — pick based on what's simplest to verify today:

- **(a) Minimal fix:** leave embeddings generation as a manual prerequisite step for now (documented clearly), and just fix the tenant-scoping bug so it's *safe* to run manually. This unblocks today's verification without expanding scope further.
- **(b) Fuller fix:** have `initialize_gat()` automatically call `fetch_graph_from_neo4j` → `run_node2vec` → `store_embeddings_in_neo4j` as a first step if no embeddings are found for that tenant, before proceeding to GAT training. This is more complete but expands today's change surface.

**Recommendation: do (a) for now.** Note (b) as a fast-follow. The goal today is closing the tenant-isolation safety bug and finishing verification of the caching/invalidation/background-retraining work already built — not expanding the pipeline further in the same pass.

## Verification steps (required, real output)

1. **Run embeddings generation for Tenant A only** (the `org_id`/`engagement_id` used throughout today's testing), using the new CLI/script interface from §4.
2. **Query Neo4j directly** to confirm only Tenant A's nodes now have an `embedding` property, and that a *different* tenant's nodes (even ones sharing an `objectid` with Tenant A, if any exist from today's testing) do NOT have embeddings written:
   ```cypher
   MATCH (n) WHERE n.embedding IS NOT NULL RETURN n.org_id, count(n)
   ```
   This should show embeddings only under Tenant A's `org_id`, count matching Tenant A's actual node count for that engagement.
3. **Re-run the GAT training verification from earlier** (`/ingest/bloodhound` → poll `/gnn/status`) — this time it should proceed past the "No embedded nodes found" error and either complete training (`status: ready`) or fail on some new, different, legitimate issue — which would be useful new information, not a regression.
4. **Confirm `gnn/cache/{org_id}/{engagement_id}/` gets real `path_gat.pt`, `graph_tensors.pt`, `metadata.json` files on disk** once training succeeds — `ls` the directory, don't just trust the status string.

## Out of scope

- Automated embeddings-on-demand (§5 option b) — explicitly deferred.
- Any change to Node2Vec hyperparameters, model architecture, or training logic beyond what's needed for tenant scoping.
