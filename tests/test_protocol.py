from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from reference.cases import build_cases
from reference.oracle import encode_case, simulate_case

ROOT = Path("/app")
ENV = Path("/app/environment")
REFERENCE = Path("/tests/reference")
AGENT_DIR = ENV


def _env():
    path = os.environ.get("PATH", "")
    path = f"/usr/local/go/bin:/opt/venv/bin:{path}"
    return {
        "GOPROXY": "off",
        "GOFLAGS": "-mod=mod",
        "GOCACHE": "/tmp/gocache",
        "PATH": path,
    }


def _build(dirpath: Path) -> Path:
    r = subprocess.run(
        ["go", "build", "-o", "lease_sim", "."],
        cwd=str(dirpath),
        check=False,
        capture_output=True,
        text=True,
        env=_env(),
        timeout=120,
    )
    if r.returncode != 0:
        raise AssertionError(f"go build failed in {dirpath}: {r.stderr}")
    return dirpath / "lease_sim"


def _write_case(path: Path, case: dict) -> Path:
    fn = path / f"{case['case_id']}.json"
    fn.write_text(json.dumps(case))
    return fn


def _run(binary: Path, case_file: Path) -> dict:
    p = subprocess.run(
        [str(binary), str(case_file)],
        cwd=str(binary.parent),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert p.returncode == 0
    data = p.stdout.strip()
    assert data
    return json.loads(data)


def _run_bytes(binary: Path, case_file: Path) -> bytes:
    p = subprocess.run(
        [str(binary), str(case_file)],
        cwd=str(binary.parent),
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert p.returncode == 0
    assert p.stderr == b""
    assert p.stdout
    return p.stdout


def _run_bad_input(binary: Path, case_file: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), str(case_file)],
        cwd=str(binary.parent),
        capture_output=True,
        check=False,
        timeout=20,
    )


def _build_reference_outputs(cases):
    expected = {}
    for case in cases:
        expected[case["case_id"]] = simulate_case(case)
    return expected


def _build_reference_bytes(cases):
    return {case["case_id"]: encode_case(case) for case in cases}


@pytest.fixture(scope="session")
def cases():
    return build_cases()


@pytest.fixture(scope="session")
def expected_cases(cases):
    return _build_reference_outputs(cases)


@pytest.fixture(scope="session")
def expected_bytes(cases):
    return _build_reference_bytes(cases)


@pytest.fixture(scope="session")
def agent_binary():
    d = Path(tempfile.mkdtemp(prefix="agent_"))
    for f in AGENT_DIR.iterdir():
        if f.is_file() and (f.suffix == ".go" or f.name == "go.mod"):
            shutil.copy(f, d / f.name)
        elif f.is_file() and f.name in {"go.sum"}:
            continue
    if not (d / "go.mod").exists():
        (d / "go.mod").write_text("module leasefence\n\ngo 1.24\n")
    return _build(d)


def _build_baseline(name):
    d = Path(tempfile.mkdtemp(prefix=f"base_{name}_"))
    base_dir = REFERENCE / "baselines" / name
    for file in base_dir.iterdir():
        if file.suffix == ".go":
            shutil.copy(file, d / file.name)
    (d / "go.mod").write_text("module leasefence\n\ngo 1.24\n")
    return _build(d)


@pytest.fixture(scope="session")
def baseline_bins():
    return {name: _build_baseline(name) for name in ["skip_quorum", "stale_token", "lost_durability"]}


def test_agent_matches_oracle(cases, expected_cases, agent_binary):
    """Match independently recomputed outcomes on every hidden schedule."""
    with tempfile.TemporaryDirectory(prefix="cases_") as td:
        td = Path(td)
        for case in cases:
            input_path = _write_case(td, case)
            got = _run(agent_binary, input_path)
            want = expected_cases[case["case_id"]]
            assert got == want


def test_malformed_json_exits_nonzero(agent_binary):
    """Reject malformed JSON input with nonzero exit and no stdout report."""
    with tempfile.TemporaryDirectory(prefix="badjson_") as td:
        input_path = Path(td) / "broken.json"
        input_path.write_text('{"case_id": "broken", "events": [')
        p = _run_bad_input(agent_binary, input_path)
        assert p.returncode != 0
        assert p.stdout == b""


def test_agent_emits_compact_output(cases, expected_bytes, agent_binary):
    """Emit exact compact JSON bytes with no stderr diagnostics."""
    with tempfile.TemporaryDirectory(prefix="compact_") as td:
        td = Path(td)
        for case in cases:
            input_path = _write_case(td, case)
            got = _run_bytes(agent_binary, input_path)
            assert got == expected_bytes[case["case_id"]]


def test_agent_reproducible(cases, expected_cases, agent_binary):
    """Produce identical oracle-matching traces on repeated executions."""
    with tempfile.TemporaryDirectory(prefix="repro_") as td:
        td = Path(td)
        for case in cases:
            input_path = _write_case(td, case)
            got1 = _run(agent_binary, input_path)
            got2 = _run(agent_binary, input_path)
            assert got1 == got2 == expected_cases[case["case_id"]]


def test_determinism_over_runs(cases, expected_cases, agent_binary):
    """Remain deterministic across three complete schedules."""
    with tempfile.TemporaryDirectory(prefix="det_") as td:
        td = Path(td)
        for case in cases:
            input_path = _write_case(td, case)
            a = _run(agent_binary, input_path)
            b = _run(agent_binary, input_path)
            c = _run(agent_binary, input_path)
            assert a == b == c == expected_cases[case["case_id"]]


def _diverges(binary, expected_cases, baseline_name, cases):
    with tempfile.TemporaryDirectory(prefix=f"base_run_{baseline_name}_") as td:
        td = Path(td)
        for case in cases:
            input_path = _write_case(td, case)
            got = _run(binary, input_path)
            want = expected_cases[case["case_id"]]
            if got != want:
                return True
        return False


def test_baseline_skip_quorum_diverges(cases, expected_cases, baseline_bins):
    """Reject a ledger that grants leases without quorum."""
    assert _diverges(baseline_bins["skip_quorum"], expected_cases, "skip_quorum", cases)


def test_baseline_stale_token_diverges(cases, expected_cases, baseline_bins):
    """Reject a ledger that accepts stale fencing tokens."""
    assert _diverges(baseline_bins["stale_token"], expected_cases, "stale_token", cases)


def test_baseline_lost_durability_diverges(cases, expected_cases, baseline_bins):
    """Reject a ledger that loses acknowledged recovered metadata."""
    assert _diverges(baseline_bins["lost_durability"], expected_cases, "lost_durability", cases)


def test_edge_rows_are_present(cases, expected_cases):
    """Exercise declined writes, unknown rows, recovery, and target normalization."""
    edge = {case["case_id"]: case for case in cases if case["seed"] in {9000, 9001}}
    assert set(edge) == {"case-0044", "case-0045"}
    first = expected_cases["case-0044"]["results"]
    assert first[0]["status"] == "granted" and first[0]["token"] == 1
    assert first[1]["status"] == "rejected" and first[1]["token"] == 1
    assert first[2]["status"] == "rejected" and first[2]["token"] == 99
    assert first[3]["status"] == "ignored" and first[3]["token"] == 123
    assert first[4]["status"] == "committed" and first[4]["expires_at"] == 3
    second = expected_cases["case-0045"]["results"]
    assert second[3]["status"] == "committed"
    assert second[5]["status"] == "rejected" and second[5]["token"] == 1
