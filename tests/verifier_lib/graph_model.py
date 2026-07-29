"""Artifact graph closure helpers."""
from __future__ import annotations

from collections import deque
from typing import Any

ALLOWED = {"contains", "depends-on", "built-from", "packaged-from", "derived-from"}

def reachable_closure(root: str, graph: dict[str, Any]) -> list[str]:
    adjacency: dict[str, list[str]] = {}
    for edge in graph["edges"]:
        if edge["relation"] not in ALLOWED:
            continue
        adjacency.setdefault(edge["from"], []).append(edge["to"])
    seen: list[str] = []
    queue = deque([root])
    visited: set[str] = set()
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        seen.append(node)
        for nxt in adjacency.get(node, []):
            if nxt not in visited:
                queue.append(nxt)
    return seen
