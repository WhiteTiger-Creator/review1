"""Residual graph reachability helper."""
from __future__ import annotations

from collections import deque

from fyop.topology.graph import YardGraph


def can_loco_reach_lead(
    graph: YardGraph,
    loco_track: str,
    failed_switches: set[str],
) -> bool:
    """Residual-graph locomotive closure check against LEAD via BFS."""
    if loco_track == "LEAD":
        return True
    failed = set(failed_switches or [])
    seen: set[str] = {loco_track}
    q: deque[str] = deque([loco_track])
    while q:
        cur = q.popleft()
        for edge in graph.edges_from(cur):
            if edge.id in failed:
                continue
            nxt = edge.to_track if edge.from_track == cur else edge.from_track
            if nxt in seen:
                continue
            if nxt == "LEAD":
                return True
            seen.add(nxt)
            q.append(nxt)
    return False
