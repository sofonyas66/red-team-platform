---

## Replace pyg-lib-dependent Node2Vec with pure-PyTorch implementation

**Root cause:** This host's CPU lacks AVX/AVX2 (confirmed via `/proc/cpuinfo`: only up to SSE4.1). PyG's `Node2Vec` class hard-requires `pyg-lib`'s compiled random-walk sampler, whose prebuilt wheel assumes a modern CPU baseline and crashes silently (no Python traceback, process killed) when it hits an unsupported instruction. Same root cause class as the earlier numpy `X86_V2` build failure, but with no equivalent rebuild-from-source escape hatch for `pyg-lib`.

**Fix:** In `gnn/embeddings.py`'s `run_node2vec()`, replace the `torch_geometric.nn.Node2Vec` class with a manual implementation:
1. Random walk generation: implement in pure Python/PyTorch using the existing `data.edge_index` adjacency — for each node, sample `num_walks` walks of `walk_length` steps using uniform random neighbor selection (standard Node2Vec with p=q=1 is equivalent to DeepWalk's walk strategy; note if the existing config implies biased p/q walks, those need the full Node2Vec transition logic, not just uniform DeepWalk — check the current `Node2Vec(...)` call's `p=`/`q=` args first, since unchanged defaults of p=1,q=1 simplify this considerably)
2. Skip-gram training: use `torch.nn.Embedding` for the embedding table and a standard skip-gram with negative sampling loss, trained with a plain PyTorch optimizer loop (`torch.optim.SparseAdam`, same as PyG's `Node2Vec.loader()` used internally) — no `pyg-lib` import anywhere.
3. Keep the function signature and return shape identical (`embeddings` tensor of shape `[num_nodes, dimensions]`) so nothing downstream (`store_embeddings_in_neo4j`, etc.) needs to change.
4. Remove `pyg-lib` from `pyproject.toml`/requirements if nothing else in the codebase needs it — check first with `grep -rn "pyg_lib\|pyg-lib" --include="*.py"`.

**Verification required (real output, not claims):**
- Run `python -m gnn.embeddings --org_id 41931682-4dc6-4b6b-a799-c05c2516ec6a --engagement_id c3e48674-6e9e-4bb5-a6c2-3e58d9aa92d4` to completion without a crash
- Paste the full terminal output including the final `Verification: N nodes have D-dim embeddings` line the script already prints
- Run the Neo4j isolation query and paste output: `MATCH (n) WHERE n.embedding IS NOT NULL RETURN n.org_id, count(n)` — expect 294 under tenant A, 0 under tenant B

---

--- UPDATE 2026-10-14 ---
Fix applied in gnn/embeddings.py (117 insertions, 67 deletions).
- Removed torch_geometric imports; replaced with manual pure-PyTorch walks (uniform p=q=1, DeepWalk-equivalent).
- Skip-gram: torch.nn.Embedding (sparse=True), SparseAdam optimizer, negative sampling (3 negs, window=8).
- data.num_nodes + data.edge_index preserved; store_embeddings_in_neo4j unchanged.
- Verification blocked: numpy built with X86_V2 (machine: SSE4.1 only); torch 2.14.1 also X86_V2. Cannot import either until rebuilt or replaced with baseline-compatible build.
