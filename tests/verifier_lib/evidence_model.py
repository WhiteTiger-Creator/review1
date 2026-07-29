"""Expected decision and evidence helpers."""
from __future__ import annotations

from typing import Any

from verifier_lib.canonical_cbor import validate_cbor
from verifier_lib.canonical_json import digest_bytes


def evidence_digest(data: bytes) -> str:
    return digest_bytes(data)

def build_decision(request_digest: str, evaluation_epoch: int, root: str, artifact_results: list[Any], evidence: bytes) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "request_digest": request_digest,
        "evaluation_epoch": evaluation_epoch,
        "root_artifact": root,
        "decision": "approve",
        "reason": None,
        "artifact_results": artifact_results,
        "effective_revocations": [],
        "legacy_evidence_used": [],
        "evidence_digest": evidence_digest(evidence),
    }

def validate_decision(decision: dict[str, Any], evidence: bytes) -> None:
    validate_cbor(evidence)
    if decision["evidence_digest"] != evidence_digest(evidence):
        raise ValueError("evidence digest mismatch")
