"""Documented JSON encoding, publication rounding, and digest bindings.

See ``docs/artifacts.md``, sections *Rounding*, *Documented encoding*, and
*Digest bindings*.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pmwio.constants import PUBLICATION_DIGITS


def compact_bytes(payload: Any) -> bytes:
    """Serialize ``payload`` to the documented encoding both digests hash."""
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
        ensure_ascii=True,
    )
    return text.encode("utf-8")


def content_digest(payload: Any) -> str:
    """Lowercase hex SHA-256 of the documented encoding of ``payload``."""
    return hashlib.sha256(compact_bytes(payload)).hexdigest()


def seal(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Store the digest of ``payload`` without ``key`` into ``payload[key]``."""
    body = {
        name: value
        for name, value in payload.items()
        if name != key and name != "provenance"
    }
    payload[key] = content_digest(body)
    return payload


def publish_float(value: float) -> float:
    """Round one published float, mapping a rounded ``-0.0`` onto ``0.0``."""
    rounded = round(float(value), PUBLICATION_DIGITS)
    return 0.0 if rounded == 0.0 else rounded
