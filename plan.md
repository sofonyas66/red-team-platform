### Understanding
The current templated fallback plan in `backend/llm/planner.py` is generic and does not reflect actual attack path nodes or edges.
I will update `_templated_plan` to iterate over `scored_paths[0]['nodes']` and `['rels']` to create a phase-by-phase plan mapping known edge types to T-IDs, while identifying the actor name.

### Edits
File: `backend/llm/planner.py`
Change `_templated_plan` to use a mapping of rel types to T-IDs and generate phases dynamically based on path nodes/rels.

### Files affected
`backend/llm/planner.py`
