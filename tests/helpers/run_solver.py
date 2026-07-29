"""Subprocess helpers for driving /app/bin/emsolve."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

BIN = Path("/app/bin/emsolve")


def run_solver(
    mesh: Path,
    modes: int,
    output: Path,
    *,
    config: Path | None = None,
    checkpoint: Path | None = None,
    checkpoint_after: int | None = None,
    resume: Path | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    command = [str(BIN), "--mesh", str(mesh), "--modes", str(modes), "--output", str(output)]
    if config is not None:
        command.extend(["--config", str(config)])
    if checkpoint is not None:
        command.extend(["--checkpoint", str(checkpoint)])
    if checkpoint_after is not None:
        command.extend(["--checkpoint-after", str(checkpoint_after)])
    if resume is not None:
        command.extend(["--resume", str(resume)])
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def load_modes(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
