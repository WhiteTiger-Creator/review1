"""Canonical runbook checksum helpers for fixture mutation only.

These helpers implement the public checksum procedure from
``/app/docs/runbook_release_profile.md``. They do not plan releases,
resolve replacements, or construct reports.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def _sort_utf8(values: list[str]) -> list[str]:
    return sorted(values, key=lambda v: v.encode("utf-8"))


def compute_runbook_checksum_from_raw(raw: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON payload for a runbook mapping."""
    steps = sorted(raw["steps"], key=lambda s: s["step_id"].encode("utf-8"))
    payload = {
        "runbook_id": raw["runbook_id"],
        "version": raw["version"],
        "plan_rank": raw["plan_rank"],
        "requires": _sort_utf8(list(raw["requires"])),
        "conflicts": _sort_utf8(list(raw["conflicts"])),
        "replaces": _sort_utf8(list(raw["replaces"])),
        "provides_runbook_ids": _sort_utf8(list(raw["provides_runbook_ids"])),
        "allowed_api_revisions": _sort_utf8(list(raw["allowed_api_revisions"])),
        "allowed_database_revisions": _sort_utf8(
            list(raw["allowed_database_revisions"])
        ),
        "steps": [
            {
                "step_id": step["step_id"],
                "step_rank": step["step_rank"],
                "step_kind": step["step_kind"],
                "requires_step_ids": _sort_utf8(list(step["requires_step_ids"])),
                "required_capabilities": _sort_utf8(
                    list(step["required_capabilities"])
                ),
                "provided_capabilities": _sort_utf8(
                    list(step["provided_capabilities"])
                ),
                "api_operation_id_or_null": step["api_operation_id_or_null"],
                "http_method_or_null": step["http_method_or_null"],
                "request_content_type_or_null": step["request_content_type_or_null"],
                "accepted_statuses": sorted(step["accepted_statuses"]),
                "database_action_or_null": step["database_action_or_null"],
                "retry_mode": step["retry_mode"],
                "idempotency_key_source_or_null": step[
                    "idempotency_key_source_or_null"
                ],
            }
            for step in steps
        ],
    }
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def recompute_runbook_file_checksum(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    digest = compute_runbook_checksum_from_raw(raw)
    raw["checksum_sha256"] = digest
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            raw, fh, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
    return digest
