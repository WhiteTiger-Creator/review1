"""JSON serialization utilities: canonical compact and pretty formats."""
from __future__ import annotations

import hashlib
import json


def canonical(obj: object) -> str:
    """Compact JSON with recursively sorted keys — used for all hash inputs."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def pretty(obj: object) -> str:
    """2-space indented JSON preserving insertion-order keys, with trailing newline."""
    return json.dumps(obj, indent=2, sort_keys=False) + "\n"


def sha256hex(text: str) -> str:
    """SHA-256 of a UTF-8 encoded string, returned as lowercase hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
