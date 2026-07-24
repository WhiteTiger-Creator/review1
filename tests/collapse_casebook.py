"""Shared helpers for voltage-collapse fold-map verification (no CPF solver)."""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

FOLD_MAP = Path(os.environ.get("FOLD_MAP", "/loadcrest/bin/fold-map"))
SEALED = Path(__file__).resolve().parent / "sealed_margins"


@dataclass
class TraceResult:
    """Parsed successful fold-map trace."""

    map_path: Path
    stdout: str
    critical_lambda: float
    network_sha256: str
    ramp_sha256: str
    manifest: dict
    curve: list[dict]
    events: list[dict]
    buses: list[dict]
    branches: list[dict]
    raw_zip: bytes


def fold_map_bin() -> Path:
    """Return the public fold-map wrapper path."""
    return FOLD_MAP


def write_text(path: Path, text: str) -> Path:
    """Write UTF-8 text with trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text if text.endswith("\n") else text + "\n"
    path.write_text(data, encoding="utf-8")
    return path


def run_admittance(network: Path) -> dict:
    """Run the admittance companion and parse JSON."""
    proc = subprocess.run(
        [str(FOLD_MAP), "admittance", "--network", str(network)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"admittance failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def run_trace(network: Path, ramp: Path, map_path: Path) -> TraceResult:
    """Run trace and parse the voltage-collapse map archive."""
    if map_path.exists():
        map_path.unlink()
    proc = subprocess.run(
        [
            str(FOLD_MAP),
            "trace",
            "--network",
            str(network),
            "--ramp",
            str(ramp),
            "--map",
            str(map_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"trace failed rc={proc.returncode}: {proc.stderr.strip()}")
    line = proc.stdout.strip().splitlines()[-1]
    parts = line.split()
    assert parts[0] == "FOLD_MAPPED"
    raw = map_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        curve = list(csv.DictReader(io.StringIO(zf.read("curve.csv").decode())))
        events = list(csv.DictReader(io.StringIO(zf.read("events.csv").decode())))
        buses = list(csv.DictReader(io.StringIO(zf.read("critical_bus.csv").decode())))
        branches = list(csv.DictReader(io.StringIO(zf.read("critical_branch.csv").decode())))
        names = zf.namelist()
    assert names == [
        "manifest.json",
        "curve.csv",
        "events.csv",
        "critical_bus.csv",
        "critical_branch.csv",
    ]
    return TraceResult(
        map_path=map_path,
        stdout=proc.stdout,
        critical_lambda=float(parts[2]),
        network_sha256=parts[3],
        ramp_sha256=parts[4],
        manifest=manifest,
        curve=curve,
        events=events,
        buses=buses,
        branches=branches,
        raw_zip=raw,
    )


def run_trace_expect_fail(network: Path, ramp: Path, map_path: Path) -> tuple[int, str, bytes | None]:
    """Run trace expecting failure; return rc, stderr, prior map bytes if any."""
    prior = map_path.read_bytes() if map_path.exists() else None
    proc = subprocess.run(
        [
            str(FOLD_MAP),
            "trace",
            "--network",
            str(network),
            "--ramp",
            str(ramp),
            "--map",
            str(map_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stderr.strip(), prior


def sealed(name: str) -> tuple[Path, Path]:
    """Return absolute sealed network/ramp paths."""
    return SEALED / f"{name}.acn", SEALED / f"{name}.rmp"


def load_margins() -> dict:
    """Load sealed margin expectations."""
    return json.loads((SEALED / "margins.json").read_text(encoding="utf-8"))


def two_bus_network(path: Path, *, p_load: float = 0.5, q_load: float = 0.2, x: float = 0.1) -> Path:
    """Write a minimal two-bus analytic network."""
    text = f"""AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1.0 0 0 0 0 0 0 0 0 0
BUS load PQ 1.0 0 0 0 0 0 {p_load} {q_load} 0 0
BRANCH l1 slack load IN 0.01 {x} 0.0 1.0 0
END
"""
    return write_text(path, text)


def two_bus_ramp(path: Path, *, dp: float = 0.3, dq: float = 0.1, step: float = 0.02) -> Path:
    """Write a two-bus loading ramp."""
    text = f"""AC_RAMP 1
DEMAND load {dp} {dq}
LIMITS 0.7 1.2
STEPS {step} 0.002 0.1
TOLERANCES 1e-6 1e-6 1e-5 1e-5
ITERATIONS 40 40 200
END
"""
    return write_text(path, text)


def shuffle_network_records(src: Path, dst: Path) -> Path:
    """Permute BUS/BRANCH record order while preserving semantics."""
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert lines[0].startswith("AC_NETWORK")
    assert lines[-1] == "END"
    body = lines[1:-1]
    buses = [ln for ln in body if ln.startswith("BUS")]
    branches = [ln for ln in body if ln.startswith("BRANCH")]
    base = [ln for ln in body if ln.startswith("BASE_MVA")]
    buses = list(reversed(buses))
    branches = list(reversed(branches))
    out = ["AC_NETWORK 1", *branches, *base, *buses, "END"]
    return write_text(dst, "\n".join(out))


def shuffle_ramp_demands(src: Path, dst: Path) -> Path:
    """Permute DEMAND record order."""
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert lines[0].startswith("AC_RAMP")
    assert lines[-1] == "END"
    body = lines[1:-1]
    demands = [ln for ln in body if ln.startswith("DEMAND")]
    other = [ln for ln in body if not ln.startswith("DEMAND")]
    demands = list(reversed(demands))
    out = ["AC_RAMP 1", *other, *demands, "END"]
    return write_text(dst, "\n".join(out))
