"""Shared I/O and candidate invocation helpers for cmake-reconciler verifier tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("CMAKE_DATA_DIR", "/app/data"))
CANDIDATE_BIN = Path(
    os.environ.get("CANDIDATE_BIN", "/app/target/release/cmake-reconciler")
)
ISOLATION_WRAPPER = Path(
    os.environ.get("ISOLATION_WRAPPER", "/tests/run_candidate_isolated.sh")
)

REQUIRED_DATA_FILES = (
    "declarations.json",
    "find_requests.ndjson",
    "provider_responses.json",
    "package_candidates.json",
    "source_overrides.json",
    "target_graph.json",
    "previous_resolution_locks.json",
    "policy.json",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def copy_data_dir(dest: Path) -> Path:
    """Copy canonical fixture data into *dest* for isolated mutation."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(DATA_DIR, dest)
    return dest


def load_report(path: Path) -> dict[str, Any]:
    return read_json(path)


def _stderr_token(stderr: str) -> str | None:
    for line in stderr.splitlines():
        line = line.strip()
        if line and ":" in line:
            return line.split(":", 1)[0].strip()
    return None


def run_candidate(
    data_dir: Path,
    report_out: Path,
    *,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    """Execute the native reconciler, preferring the isolation wrapper when available."""
    report_out.parent.mkdir(parents=True, exist_ok=True)
    cli_args = [
        "reconcile",
        "--data-dir",
        str(data_dir),
        "--report-out",
        str(report_out),
    ]
    use_wrapper = (
        os.environ.get("CANDIDATE_DIRECT", "0") != "1"
        and ISOLATION_WRAPPER.is_file()
        and shutil.which("bash") is not None
    )
    if use_wrapper:
        cmd = ["bash", str(ISOLATION_WRAPPER), str(CANDIDATE_BIN), "--", *cli_args]
    else:
        cmd = [str(CANDIDATE_BIN), *cli_args]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def run_ok(data_dir: Path, report_out: Path) -> dict[str, Any]:
    proc = run_candidate(data_dir, report_out)
    assert proc.returncode == 0, (
        f"candidate reconcile failed\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert report_out.is_file(), "expected resolution_report.json"
    return load_report(report_out)


def run_ok_bytes(data_dir: Path, report_out: Path) -> bytes:
    proc = run_candidate(data_dir, report_out)
    assert proc.returncode == 0, proc.stderr
    return report_out.read_bytes()


def assert_fatal(
    data_dir: Path,
    report_out: Path,
    token: str,
) -> subprocess.CompletedProcess[str]:
    proc = run_candidate(data_dir, report_out)
    assert proc.returncode != 0, (
        f"expected fatal exit for token {token!r}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert _stderr_token(proc.stderr) == token, proc.stderr
    assert not report_out.exists(), "report must be absent on whole-run fatal"
    assert not report_out.with_name(report_out.name + ".tmp").exists(), (
        "report temp sibling must be absent on whole-run fatal"
    )
    return proc


def restrict_configure_requests(data_dir: Path, configure_request_ids: list[str]) -> None:
    policy = read_json(data_dir / "policy.json")
    wanted = set(configure_request_ids)
    policy["configure_requests"] = [
        row
        for row in policy["configure_requests"]
        if row["configure_request_id"] in wanted
    ]
    write_json(data_dir / "policy.json", policy)


def seed_matching_lock_sections(
    data_dir: Path,
    *,
    lock_id: str,
    configure_request_id: str,
) -> None:
    """Populate *lock_id* with digests from a reference reconcile of *data_dir*."""
    from reference.engine import reconcile

    report = reconcile(data_dir)
    sections_by_dependency: dict[str, dict[str, Any]] = {}
    for row in report["lock_section_rows"]:
        if row["configure_request_id"] != configure_request_id:
            continue
        dep = row["dependency_name"]
        sections_by_dependency.setdefault(dep, {})[row["section"]] = {
            "input_digest": row["input_digest"],
            "result_digest": row["result_digest"],
            "stored_result": {},
        }
    locks_doc = read_json(data_dir / "previous_resolution_locks.json")
    for lock in locks_doc["locks"]:
        if lock["lock_id"] == lock_id:
            lock["sections_by_dependency"] = sections_by_dependency
    write_json(data_dir / "previous_resolution_locks.json", locks_doc)


def binary_ready() -> bool:
    return CANDIDATE_BIN.is_file() and (
        sys.platform == "win32" or os.access(CANDIDATE_BIN, os.X_OK)
    )
