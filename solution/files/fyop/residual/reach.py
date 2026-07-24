"""Residual graph reachability: loco can reach LEAD (ending on LEAD is not required)."""
from __future__ import annotations

from collections import deque

from fyop.topology.graph import YardGraph


def can_loco_reach_lead(
    graph: YardGraph,
    loco_track: str,
    failed_switches: set[str],
) -> bool:
    """BFS reachability from loco_track to LEAD skipping failed switches.

    Returns True when any non-failed path from loco_track to LEAD exists.
    The loco does not have to end ON LEAD — reachability is the contract.
    """
    if loco_track is None:
        return False
    if loco_track == "LEAD":
        return True
    seen: set[str] = {loco_track}
    q: deque[str] = deque([loco_track])
    while q:
        cur = q.popleft()
        for edge in graph.edges_from(cur):
            if edge.id in failed_switches:
                continue
            nxt = edge.to_track if edge.from_track == cur else edge.from_track
            if nxt in seen:
                continue
            if nxt == "LEAD":
                return True
            seen.add(nxt)
            q.append(nxt)
    return False
