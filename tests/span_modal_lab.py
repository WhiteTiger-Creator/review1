"""Helpers for SpanForge modal calibration verifier cases.

Constructs small model/survey/plan fixtures, invokes the public binary,
parses MCR records, and manages isolated report paths. Does not implement
a general eigen-solver, optimizer, cluster assignment, or sensitivity analyzer.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

SEALED_DIR = Path(__file__).resolve().parent / "sealed_modal_cases"


def spanforge_root() -> Path:
    env = os.environ.get("SPANFORGE_ROOT")
    if env:
        return Path(env)
    docker = Path("/opt/spanforge")
    if docker.exists():
        return docker
    return Path(__file__).resolve().parents[1] / "environment" / "spanforge"


def modal_reconciler() -> Path:
    root = spanforge_root()
    # Prefer a real executable over the Docker absolute-path wrapper when
    # authoring/testing outside /opt/spanforge.
    for candidate in (
        root / "libexec" / "modal-reconciler",
        root / "target" / "release" / "modal-reconciler",
        Path("/opt/spanforge/libexec/modal-reconciler"),
        root / "bin" / "modal-reconciler",
    ):
        if candidate.exists() and os.access(candidate, os.X_OK):
            # Skip shell wrappers that hardcode /opt when libexec is missing.
            if candidate.name == "modal-reconciler" and candidate.parent.name == "bin":
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                libexec = Path("/opt/spanforge/libexec/modal-reconciler")
                if "/opt/spanforge/libexec" in text and not libexec.exists():
                    continue
            return candidate
    raise FileNotFoundError("modal-reconciler binary not found")


def write_json(path: Path, obj: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return path


def run_spectrum(model: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(modal_reconciler()), "spectrum", "--model", str(model)],
        capture_output=True,
        text=True,
        check=False,
    )


def run_calibrate(
    model: Path,
    survey: Path,
    plan: Path,
    report: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(modal_reconciler()),
            "calibrate",
            "--model",
            str(model),
            "--survey",
            str(survey),
            "--plan",
            str(plan),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def parse_mcr(text: str) -> dict[str, Any]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    rec: dict[str, Any] = {"groups": [], "pairs": [], "raw": text}
    for ln in lines:
        parts = ln.split(" ")
        key = parts[0]
        if key == "MODEL_SHA256":
            rec["model_sha256"] = parts[1]
        elif key == "SURVEY_SHA256":
            rec["survey_sha256"] = parts[1]
        elif key == "PLAN_SHA256":
            rec["plan_sha256"] = parts[1]
        elif key == "OBJECTIVE":
            rec["objective_total"] = float(parts[1])
            rec["objective_modal"] = float(parts[2])
            rec["objective_reg"] = float(parts[3])
        elif key == "ITERATIONS":
            rec["iterations"] = int(parts[1])
        elif key == "PROJECTED_GRADIENT_INF":
            rec["projected_gradient_inf"] = float(parts[1])
        elif key == "FINAL_STEP_INF":
            rec["final_step_inf"] = float(parts[1])
        elif key == "NUMERICAL_RANK":
            rec["numerical_rank"] = int(parts[1])
            rec["group_count"] = int(parts[2])
        elif key == "CONFIDENCE":
            rec["confidence"] = parts[1]
        elif key == "GROUP":
            rec["groups"].append(
                {
                    "id": parts[1],
                    "theta": float(parts[2]),
                    "lower": float(parts[3]),
                    "upper": float(parts[4]),
                    "reference": float(parts[5]),
                    "bound": parts[6],
                    "gconf": parts[7],
                    "score": float(parts[8]),
                    "rank": int(parts[9]),
                }
            )
        elif key == "PAIR":
            rec["pairs"].append(
                {
                    "measured": parts[1],
                    "predicted": parts[2],
                    "meas_cent": float(parts[3]),
                    "pred_cent": float(parts[4]),
                    "freq_res": float(parts[5]),
                    "mac": float(parts[6]),
                    "cost": float(parts[7]),
                }
            )
        elif key == "STATUS":
            rec["status"] = parts[1]
    return rec


def stderr_code(proc: subprocess.CompletedProcess[str]) -> str | None:
    err = (proc.stderr or "").strip()
    if not err:
        return None
    try:
        return json.loads(err.splitlines()[-1]).get("code")
    except json.JSONDecodeError:
        return None


def isolated_workdir() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="spanfit_")


def load_sealed(name: str) -> Path:
    p = SEALED_DIR / name
    if not p.exists():
        raise FileNotFoundError(p)
    return p


def copy_sealed_triplet(name: str, dest: Path) -> tuple[Path, Path, Path]:
    src = load_sealed(name)
    dest.mkdir(parents=True, exist_ok=True)
    model = dest / "model.json"
    survey = dest / "survey.json"
    plan = dest / "plan.json"
    shutil.copy(src / "model.json", model)
    shutil.copy(src / "survey.json", survey)
    shutil.copy(src / "plan.json", plan)
    return model, survey, plan


def base_plan(**overrides: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "format": "bridge-calibration-plan-v1",
        "mode_count": 2,
        "frequency_weight": 1.0,
        "shape_weight": 1.0,
        "regularization_weight": 0.01,
        "cluster_relative_tolerance": 0.0001,
        "pairing_frequency_gate": 0.35,
        "finite_difference_step": 0.0001,
        "gradient_tolerance": 1e-8,
        "step_tolerance": 1e-9,
        "objective_tolerance": 1e-12,
        "rank_tolerance": 1e-8,
        "max_iterations": 120,
    }
    plan.update(overrides)
    return plan


def two_dof_analytic_model() -> dict[str, Any]:
    return {
        "format": "bridge-modal-model-v1",
        "dofs": ["D01", "D02"],
        "mass": [[1.0, 0.0], [0.0, 1.0]],
        "fixed_stiffness": [[2.0, -1.0], [-1.0, 2.0]],
        "groups": [
            {
                "group_id": "cable",
                "lower": 0.5,
                "upper": 1.5,
                "initial": 1.0,
                "reference": 1.0,
                "contribution": [[0.2, 0.0], [0.0, 0.2]],
            }
        ],
    }
