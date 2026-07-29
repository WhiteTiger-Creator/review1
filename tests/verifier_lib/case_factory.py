"""Hidden case generation for verifier tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

APP = Path("/app")
BIN = APP / "target" / "release" / "admission-gateway"

def build_hidden_case(seed: int, tmp: Path) -> dict[str, Path]:
    workspace = tmp / f"case-{seed:x}"
    shutil.copytree(APP, workspace)
    request_path = workspace / "requests" / "release.json"
    request = json.loads(request_path.read_text())
    request["evaluation_epoch"] = 100 + (seed % 7)
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    return {
        "workspace": workspace,
        "request": request_path,
        "output": tmp / f"out-{seed:x}",
    }

def permute_request_paths(request: dict[str, Any]) -> dict[str, Any]:
    out = dict(request)
    out["envelopes"] = list(reversed(out["envelopes"]))
    return out
