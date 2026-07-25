"""Canonical JSON serialization and SHA-256 digests."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compact_json(value: Any) -> str:
    """Serialize to compact canonical JSON (sorted keys, no insignificant whitespace)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_json(value: Any) -> str:
    """Serialize report JSON with two-space indent and trailing newline."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def sha256_hex(value: Any) -> str:
    """SHA-256 digest of compact canonical JSON over UTF-8."""
    payload = compact_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
