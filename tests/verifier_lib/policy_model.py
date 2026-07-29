"""Policy, delegation, and threshold modeling."""
from __future__ import annotations

from typing import Any


def namespace_matches(pattern: str, namespace: str) -> bool:
    if pattern == "**":
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return namespace == prefix or namespace.startswith(prefix + "/")
    return namespace == pattern

def delegation_allows(record: dict[str, Any], principal: str, tenant: str, namespace: str, predicate: str, media_type: str, epoch: int) -> bool:
    if record["subject_principal"] != principal or record["tenant"] != tenant:
        return False
    if epoch < record["valid_from_epoch"]:
        return False
    end = record.get("valid_through_epoch")
    if end is not None and epoch > end:
        return False
    if not namespace_matches(record["namespace_pattern"], namespace):
        return False
    if predicate not in record["predicates"]:
        return False
    allowed = record.get("artifact_media_types") or []
    return not allowed or media_type in allowed

def threshold_satisfied(approvals: list[tuple[str, str]], minimum: int) -> bool:
    principals = sorted({principal for _, principal in approvals})
    return len(principals) >= minimum

def canonical_satisfying_set(approvals: list[tuple[str, str]], minimum: int) -> list[str]:
    principals = sorted({principal for _, principal in approvals})
    return principals[:minimum]
