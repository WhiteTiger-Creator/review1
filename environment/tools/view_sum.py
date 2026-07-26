#!/usr/bin/env python3
import hashlib
import json
import sys


def sort_edges(edges):
    return sorted(
        edges,
        key=lambda e: (e.get("module_path", ""), e.get("version", "")),
    )


raw = sys.stdin.read()
doc = json.loads(raw)
if isinstance(doc, dict) and "edges" in doc:
    edges = doc["edges"]
else:
    edges = doc
edges = sort_edges(edges)
payload = json.dumps(edges, sort_keys=True, separators=(",", ":")).encode()
print(hashlib.sha256(payload).hexdigest())
