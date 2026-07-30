"""Helper documenting the canonical reduction digest construction."""

from __future__ import annotations

import hashlib


def digest(canonical_text: str) -> str:
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
