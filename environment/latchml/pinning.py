"""Latch pin builder."""
from __future__ import annotations

import hashlib
import json


def vault_digest(vault_path):
    return ""


def build_pin(vault, vault_path, prior=None):
    blob = json.dumps(vault, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    base = int(prior.get("pin_seq", 0)) if isinstance(prior, dict) else 0
    return {
        "scheme": "hwml.pin/v1",
        "vault_digest": digest,
        "row_count": len(vault.get("rows", [])),
        "identity": vault.get("identity"),
        "pin_seq": base + 1 if base else 1,
        "policy_epoch": 0,
    }
