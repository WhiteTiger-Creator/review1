"""Yard topology: track nodes, switch edges, and graph with BFS pathfinding."""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TrackNode:
    id: str
    type: str
    max_cars: int
    max_length_units: int


@dataclass(frozen=True)
class SwitchEdge:
    id: str
    from_track: str
    to_track: str
    length_m: float


class YardGraph:
    def __init__(self, tracks: dict[str, TrackNode], edges: list[SwitchEdge]) -> None:
        self._tracks: dict[str, TrackNode] = dict(tracks)
        self._edges: list[SwitchEdge] = list(edges)

    def get_track(self, track_id: str) -> Optional[TrackNode]:
        return self._tracks.get(track_id)

    def get_all_tracks(self) -> dict[str, TrackNode]:
        return dict(self._tracks)

    def track_ids(self) -> set[str]:
        return set(self._tracks.keys())

    def edges_from(self, track_id: str) -> list[SwitchEdge]:
        """Return all switch edges incident to track_id (undirected)."""
        return [
            e for e in self._edges
            if e.from_track == track_id or e.to_track == track_id
        ]

    def find_path(self, from_id: str, to_id: str, failed_switches: set[str]) -> Optional[list[SwitchEdge]]:
        """BFS shortest path from from_id to to_id, skipping failed switch ids."""
        if from_id == to_id:
            return []
        came_via: dict[str, SwitchEdge] = {}
        prev: dict[str, str] = {}
        seen: set[str] = {from_id}
        q: deque[str] = deque([from_id])
        while q:
            cur = q.popleft()
            for edge in self.edges_from(cur):
                if edge.id in failed_switches:
                    continue
                nxt = edge.to_track if edge.from_track == cur else edge.from_track
                if nxt in seen:
                    continue
                seen.add(nxt)
                came_via[nxt] = edge
                prev[nxt] = cur
                if nxt == to_id:
                    path: list[SwitchEdge] = []
                    walk = to_id
                    while walk != from_id:
                        path.append(came_via[walk])
                        walk = prev[walk]
                    path.reverse()
                    return path
                q.append(nxt)
        return None


def load_yard_graph(yard_dir: Path) -> YardGraph:
    """Load YardGraph from topology.json in yard_dir."""
    topo = json.loads((yard_dir / "topology.json").read_text())
    tracks: dict[str, TrackNode] = {}
    for t in topo["tracks"]:
        tracks[t["id"]] = TrackNode(
            id=t["id"],
            type=t["type"],
            max_cars=int(t["max_cars"]),
            max_length_units=int(t["max_length_units"]),
        )
    edges: list[SwitchEdge] = []
    for s in topo["switches"]:
        edges.append(SwitchEdge(
            id=s["id"],
            from_track=s["from_track"],
            to_track=s["to_track"],
            length_m=float(s["length_m"]),
        ))
    return YardGraph(tracks, edges)
