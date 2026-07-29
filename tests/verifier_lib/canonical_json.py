"""Canonical JSON helpers."""
from __future__ import annotations

import json
from typing import Any


def parse_strict(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_reject_duplicates)

def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key: {key}")
        seen.add(key)
        out[key] = value
    return out

def canonicalize(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def canonical_bytes(value: Any) -> bytes:
    return canonicalize(value).encode()

def digest_bytes(data: bytes) -> str:
    import hashlib
    return f"sha256:{hashlib.sha256(data).hexdigest()}"
