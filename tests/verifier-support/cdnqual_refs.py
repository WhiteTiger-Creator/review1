"""Sealed reference digests and floors — not an end-to-end solver."""

from __future__ import annotations

import json
from pathlib import Path

_VF_CANDIDATES = (
    Path("/opt/verifier-fixtures"),
    Path(__file__).resolve().parent.parent / "verifier-fixtures",
)


def _vf(name: str) -> Path:
    for root in _VF_CANDIDATES:
        p = root / name
        if p.is_file():
            return p
    raise FileNotFoundError(name)


def reference_public_features_sha256() -> str:
    return json.loads(_vf("public_feature_digest.json").read_text())["features_sha256"]


def reference_public_weights_sha256() -> str:
    return json.loads(_vf("public_feature_digest.json").read_text())["weights_sha256"]


def reference_public_ledger_sha256() -> str:
    return json.loads(_vf("public_feature_digest.json").read_text())["ledger_sha256"]


def reference_hidden_features_sha256() -> str:
    return json.loads(_vf("hidden_feature_digest.json").read_text())["features_sha256"]


def reference_hidden_bout_ids() -> list[str]:
    return list(json.loads(_vf("holdout_floors.json").read_text())["expected_bout_ids"])


def reference_lambda7_weights_sha256() -> str:
    return json.loads(_vf("perturbation_refs.json").read_text())["lambda7_weights_sha256"]


def reference_public_payload_hash() -> str:
    return json.loads(_vf("public_eval_ledger.json").read_text())["payload_hash"]


def reference_hidden_payload_hash() -> str:
    return json.loads(_vf("hidden_eval_ledger.json").read_text())["payload_hash"]
