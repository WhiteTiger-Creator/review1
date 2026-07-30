"""Verifier-side digest helpers mirroring IRC lineage_proof / router_digest."""

from __future__ import annotations

import hashlib


def sha256_hex16(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
