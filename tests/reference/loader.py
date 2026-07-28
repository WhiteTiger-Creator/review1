"""Load all data-dir inputs (JSON + NDJSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "declarations.json",
    "find_requests.ndjson",
    "provider_responses.json",
    "package_candidates.json",
    "source_overrides.json",
    "target_graph.json",
    "previous_resolution_locks.json",
    "policy.json",
)


class MalformedJsonError(Exception):
    """Raised when an input file cannot be parsed as JSON."""


class MissingRequiredInputError(Exception):
    """Raised when a required input file is absent."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedJsonError(str(path)) from exc


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise MalformedJsonError(f"{path}:{line_no}") from exc
        if not isinstance(value, dict):
            raise MalformedJsonError(f"{path}:{line_no}")
        rows.append(value)
    return rows


def load_data_dir(data_dir: Path) -> dict[str, Any]:
    """Load every input file from *data_dir* into a structured dict."""
    missing = [name for name in REQUIRED_FILES if not (data_dir / name).is_file()]
    if missing:
        raise MissingRequiredInputError(",".join(sorted(missing)))

    declarations_doc = _read_json(data_dir / "declarations.json")
    provider_doc = _read_json(data_dir / "provider_responses.json")
    candidates_doc = _read_json(data_dir / "package_candidates.json")
    overrides_doc = _read_json(data_dir / "source_overrides.json")
    target_graph_doc = _read_json(data_dir / "target_graph.json")
    locks_doc = _read_json(data_dir / "previous_resolution_locks.json")
    policy_doc = _read_json(data_dir / "policy.json")
    find_requests = _read_ndjson(data_dir / "find_requests.ndjson")

    return {
        "declarations": declarations_doc.get("declarations", []),
        "find_requests": find_requests,
        "providers": provider_doc.get("providers", []),
        "provider_responses": provider_doc.get("responses", []),
        "candidates": candidates_doc.get("candidates", []),
        "overrides": overrides_doc.get("overrides", []),
        "target_graph": target_graph_doc,
        "locks": locks_doc.get("locks", []),
        "policy": policy_doc,
    }
