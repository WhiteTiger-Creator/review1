"""Fixture helpers for ochre-panel-lamp-dispatch."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from panel_ref import UnsafeBoard, dispatch_from_dir

APP = Path("/app")
PANEL = APP / "panel"
OUT = APP / "out"
NOTES = APP / "notes"
CASES = Path("/tests/fixtures/cases")
BEACON = OUT / "beacon.queue"
FOLD = OUT / "runner.fold"

PANEL_FILES = (
    "clock.txt",
    "lamps.tsv",
    "flaps.tsv",
    "acknowledgements.tsv",
    "blackouts.tsv",
    "corridors.tsv",
    "bells.tsv",
    "promotions.tsv",
    "operators.tsv",
    "widths.tsv",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def panel_digests(panel: Path = PANEL) -> dict[str, str]:
    digests = {}
    for name in PANEL_FILES:
        p = panel / name
        if p.exists():
            digests[name] = sha256_file(p)
    force = panel / "FORCE_FAIL"
    if force.exists():
        digests["FORCE_FAIL"] = sha256_file(force)
    return digests


def stage_case(case_name: str) -> None:
    src = CASES / case_name
    assert src.is_dir(), f"missing case {case_name}"
    for name in PANEL_FILES:
        shutil.copy2(src / name, PANEL / name)
    force_src = src / "FORCE_FAIL"
    force_dst = PANEL / "FORCE_FAIL"
    if force_src.exists():
        shutil.copy2(force_src, force_dst)
    elif force_dst.exists():
        force_dst.unlink()


def run_dispatch(
    panel: str | Path = PANEL, out: str | Path = OUT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-C", str(APP), "dispatch", f"PANEL={panel}", f"OUT={out}"],
        text=True,
        capture_output=True,
        check=False,
    )


def notes_extras() -> list[Path]:
    if not NOTES.is_dir():
        return []
    return sorted(p for p in NOTES.iterdir() if p.name != ".keep")


def out_extras() -> list[Path]:
    allowed = {".keep", "beacon.queue", "runner.fold"}
    return sorted(p for p in OUT.iterdir() if p.name not in allowed)


@pytest.fixture
def clean_out():
    for p in (BEACON, FOLD):
        if p.exists():
            p.unlink()
    for p in notes_extras():
        p.unlink()
    yield


def assert_success(case: str):
    stage_case(case)
    before = panel_digests()
    expected_b, expected_r = dispatch_from_dir(PANEL)
    proc = run_dispatch()
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert BEACON.exists() and FOLD.exists()
    assert (OUT / ".keep").exists()
    assert notes_extras() == []
    assert out_extras() == []
    assert panel_digests() == before
    assert BEACON.read_text(encoding="utf-8") == expected_b
    assert FOLD.read_text(encoding="utf-8") == expected_r
    return expected_b, expected_r


def assert_failure(case: str, stale: bool = True):
    stage_case(case)
    OUT.mkdir(parents=True, exist_ok=True)
    if stale:
        BEACON.write_text("STALE\n", encoding="utf-8")
        FOLD.write_text("STALE\n", encoding="utf-8")
    NOTES.mkdir(parents=True, exist_ok=True)
    (NOTES / "leftover.tmp").write_text("x\n", encoding="utf-8")
    with pytest.raises(UnsafeBoard):
        dispatch_from_dir(PANEL)
    proc = run_dispatch()
    assert proc.returncode != 0
    assert not BEACON.exists()
    assert not FOLD.exists()
    assert (OUT / ".keep").exists()
    assert notes_extras() == []
    assert out_extras() == []
    return proc
