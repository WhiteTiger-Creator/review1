"""Transactional artifact writes.

See ``docs/artifacts.md``, section *Atomic, transactional writes*. Both
artifacts are rendered and validated before either destination is touched, so a
run writes both or neither.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def render(payload: Any) -> bytes:
    """Render one artifact exactly as it is stored on disk."""
    text = json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=True)
    return (text + "\n").encode("utf-8")


def _stage(path: Path, blob: bytes) -> Path:
    """Write ``blob`` to a durable temporary file beside ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    staged = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        staged.unlink(missing_ok=True)
        raise
    return staged


def write_artifacts(
    report_path: Path,
    report: Any,
    state_path: Path,
    state: Any,
) -> None:
    """Write the calibration report and the replay state atomically."""
    report_blob = render(report)
    state_blob = render(state)

    staged_report = _stage(report_path, report_blob)
    try:
        staged_state = _stage(state_path, state_blob)
    except OSError:
        staged_report.unlink(missing_ok=True)
        raise

    try:
        staged_report.replace(report_path)
        staged_state.replace(state_path)
    except OSError:
        staged_report.unlink(missing_ok=True)
        staged_state.unlink(missing_ok=True)
        raise
