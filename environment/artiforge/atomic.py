"""Artifact writes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render(payload: Any) -> bytes:
    text = json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=True)
    return (text + "\n").encode("utf-8")


def write_artifacts(
    report_path: Path,
    report: Any,
    state_path: Path,
    state: Any,
) -> None:
    """Write report then state. Partial pairs are possible if the second write fails."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(render(report))
    state_path.write_bytes(render(state))
