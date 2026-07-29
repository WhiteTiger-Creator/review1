"""Trust, migration, and revocation modeling."""
from __future__ import annotations

from typing import Any


def active_key(record: dict[str, Any], epoch: int, revocations: list[dict[str, Any]]) -> bool:
    if epoch < record["valid_from_epoch"]:
        return False
    end = record.get("valid_through_epoch")
    if end is not None and epoch > end:
        return False
    return not any(
        event["scope"] == "key" and event["target"] == record["key_id"] and event["effective_epoch"] <= epoch
        for event in revocations
    )

def resolve_principal(
    principal: str,
    tenant: str,
    namespace: str,
    predicate: str,
    epoch: int,
    migrations: list[dict[str, Any]],
) -> str:
    current = principal
    for record in migrations:
        if record["from_principal"] != current:
            continue
        if record["tenant"] != tenant:
            continue
        if epoch < record["valid_from_epoch"]:
            continue
        end = record.get("valid_through_epoch")
        if end is not None and epoch > end:
            continue
        pattern = record["namespace_pattern"]
        if pattern != "**":
            prefix = pattern.removesuffix("/**") if pattern.endswith("/**") else pattern
            if namespace != prefix and not namespace.startswith(prefix + "/"):
                continue
        if predicate not in record["predicates"]:
            continue
        current = record["to_principal"]
    return current
