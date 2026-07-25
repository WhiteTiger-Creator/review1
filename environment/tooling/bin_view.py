"""Small helper for inspecting little-endian unit payloads with struct."""

from __future__ import annotations

import struct
from pathlib import Path


def first_f32(path: str) -> float:
    raw = Path(path).read_bytes()
    return struct.unpack("<f", raw[:4])[0]
