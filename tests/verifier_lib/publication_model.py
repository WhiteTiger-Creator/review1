"""Publication snapshot helpers."""
from __future__ import annotations

import hashlib
from pathlib import Path


def snapshot_generation(output_dir: Path) -> dict[str, bytes]:
    files = {}
    for name in ("decision.json", "evidence.cbor", "generation.json"):
        path = output_dir / name
        if path.is_file():
            files[name] = path.read_bytes()
    return files

def generation_id(decision_bytes: bytes, evidence_bytes: bytes) -> str:
    material = decision_bytes + evidence_bytes
    return f"sha256:{hashlib.sha256(material).hexdigest()}"
