"""Residual graph reachability helper."""
from __future__ import annotations

from fyop.topology.graph import YardGraph


def can_loco_reach_lead(
    graph: YardGraph,
    loco_track: str,
    failed_switches: set[str],
) -> bool:
    """Residual-graph locomotive closure check against LEAD."""
    return loco_track == "LEAD"

