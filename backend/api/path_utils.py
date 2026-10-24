"""Shared path classification utilities."""

from typing import List, Tuple, Dict, Any


def classify_path(rels: List[str]) -> Tuple[str, int]:

    """Classify path risk label and count non-structural steps.
    Rules:
    Structural edges cost nothing: MemberOf, Contains, GpLink
    Control edges: AdminTo, GenericAll, GenericWrite, WriteDacl, WriteOwner,
                  Owns, AllExtendedRights, ForceChangePassword, AddMember
    Steps = number of non-structural edges.
    High: steps <= 2 AND all non-structural edges are control edges
    Medium: steps 3-4 OR steps <=2 containing any non-control edge
    Low: everything else
    steps == 0 -> Low (no vacuous High)
    """
    structural = {'MemberOf', 'Contains', 'GpLink'}
    control = {'AdminTo', 'GenericAll', 'GenericWrite', 'WriteDacl', 'WriteOwner',
               'Owns', 'AllExtendedRights', 'ForceChangePassword', 'AddMember'}
    non_structural = [r for r in rels if r not in structural]
    steps = len(non_structural)
    if steps == 0:
        return "Low", steps
    all_control = all(r in control for r in non_structural)
    if steps <= 2 and all_control:
        return "High", steps
    if 3 <= steps <= 4:
        return "Medium", steps
    if steps <= 2 and not all_control:
        return "Medium", steps
    return "Low", steps


def enrich_paths(paths: List[Dict[str, Any]], source_privileged_map: Dict[str, bool]) -> List[Dict[str, Any]]:
    enriched = []
    for p in paths:
        label, steps = classify_path(p.get("rels", []))
        source_node = p.get("source")
        source_priv = source_privileged_map.get(source_node, False)
        enriched.append({
            "source": p.get("source"),
            "target": p.get("target"),
            "hops": p.get("hops", 0),
            "steps": steps,
            "nodes": p.get("nodes", []),
            "rels": p.get("rels", []),
            "score": p.get("score"),
            "label": label,
            "source_privileged": source_priv,
        })
    return enriched


def sort_paths(paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    label_order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(
        paths,
        key=lambda x: (
            x.get("source_privileged", False),
            label_order.get(x.get("label", "Low"), 3),
            x.get("steps", 0),
            -(x.get("score") or 0)
        )
    )
