"""Shared digest helper used by shell wrappers."""

import hashlib


def hex_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
