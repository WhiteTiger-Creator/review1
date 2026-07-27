#!/usr/bin/env python3
"""SHA-256 hex helper for verifier-side digest checks."""

import hashlib


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
