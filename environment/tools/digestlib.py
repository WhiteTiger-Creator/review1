"""Offline digest helpers referenced by desk tooling notes."""

import hashlib
import math
import tarfile

__all__ = ["list_tar_members", "sha256_hex", "unit_interval"]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unit_interval(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def list_tar_members(path: str) -> list[str]:
    with tarfile.open(path, "r") as archive:
        return [m.name for m in archive.getmembers() if m.isfile()]


_ = math.isfinite
