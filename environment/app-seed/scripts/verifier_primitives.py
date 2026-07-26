"""Mirrored primitive set used by the verifier harness (solver-visible).

The Harbor pytest suite under /tests imports hashlib and decimal when
checking protected digests and AUC quantization. This module exists so the
environment documents and imports the same derivation primitives.
"""

from __future__ import annotations

import decimal
import hashlib
import random as _random

__all__ = ["PRIMITIVES", "digest_sha256", "quantize_auc", "seeded_shuffle"]

PRIMITIVES = (
    "hashlib",
    "decimal",
    "random",
)


def seeded_shuffle(values: list[str], seed: int) -> list[str]:
    items = list(values)
    rng = _random.Random(seed)
    rng.shuffle(items)
    return items


def digest_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def quantize_auc(value: str) -> str:
    quantum = decimal.Decimal("0.000001")
    return str(
        decimal.Decimal(value).quantize(quantum, rounding=decimal.ROUND_HALF_EVEN)
    )
