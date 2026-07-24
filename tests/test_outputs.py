"""Candidate-facing behavioral tests for the `vault-maze-lock` release-lock compiler.

Every test in this module builds a private, temporary copy of the fixtures
under the resolved data directory, optionally mutates that copy in a
narrowly targeted way, and runs the compiled candidate binary
(`VAULT_MAZE_LOCK_BIN`, default `/app/target/release/vault-maze-lock`)
against it via subprocess.

There is no complete planner under ``tests/``. Expectations are expressed
as property and focused assertions on the candidate report. Only
``test_28`` compares the full report against a hash-verified golden file
at ``tests/fixtures/canonical_release_report.json`` (sidecar
``canonical_release_report.sha256`` validates the golden fixture only).

Rules followed throughout this module:

* Fixtures are always copied into a fresh ``tempfile``-backed workspace
  before any mutation — the checked-in fixtures under
  ``environment/app/data`` are never modified in place.
* The candidate is exercised only as a black-box subprocess.
* Runbook checksums are recomputed with ``helpers.checksum`` whenever a
  runbook's content is mutated, so that only the intended invariant is
  exercised.

If ``VAULT_MAZE_LOCK_BIN`` does not point at an executable file, every test
that needs to run the binary is skipped with a clear message rather than
failing collection — ``pytest --collect-only`` will always report the full
set of tests in this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import sqlite3
import subprocess
import tempfile
import tomllib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers.checksum import compute_runbook_checksum_from_raw

DEFAULT_BIN = "/app/target/release/vault-maze-lock"
BIN_PATH = Path(os.environ.get("VAULT_MAZE_LOCK_BIN", DEFAULT_BIN))

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "canonical_release_report.json"
GOLDEN_SHA256_PATH = (
    Path(__file__).parent / "fixtures" / "canonical_release_report.sha256"
)

DETAIL_KEYS = {"actual_or_null", "cycle_members", "expected_or_null", "related_ids"}

REQUEST_FIELDS = {
    "request_rows",
    "selected_runbook_rows",
    "dependency_edge_rows",
    "step_rows",
    "batch_rows",
    "rejection_rows",
    "summary",
}


# ---------------------------------------------------------------------------
# Fixture data directory resolution
# ---------------------------------------------------------------------------
def resolve_data_dir() -> Path:
    env = os.environ.get("APP_DATA")
    if env:
        candidate = Path(env)
        if candidate.is_dir():
            return candidate
    container = Path("/app/data")
    if container.is_dir():
        return container
    local = Path(__file__).resolve().parent.parent / "environment" / "app" / "data"
    if local.is_dir():
        return local
    raise FileNotFoundError(
        "cannot locate the vault-maze-lock fixture data directory; "
        "set APP_DATA, or run where /app/data or environment/app/data exists"
    )


DATA_DIR = resolve_data_dir()


def _require_binary() -> None:
    if not BIN_PATH.exists() or not os.access(BIN_PATH, os.X_OK):
        pytest.skip(
            f"candidate binary not found or not executable at {BIN_PATH}; "
            "build it with 'cargo build --release --locked --offline' first "
            "(or set VAULT_MAZE_LOCK_BIN)"
        )


# ---------------------------------------------------------------------------
# Workspace management (tempfile-backed copies of the fixtures)
# ---------------------------------------------------------------------------
def copy_fixture_tree(dest: Path) -> dict[str, Path]:
    runbooks_dir = dest / "runbooks"
    shutil.copytree(DATA_DIR / "runbooks", runbooks_dir)
    release_config = dest / "release.toml"
    shutil.copy2(DATA_DIR / "release.toml", release_config)
    api_contract = dest / "flask_api_contract.json"
    shutil.copy2(DATA_DIR / "flask_api_contract.json", api_contract)
    database = dest / "vault_maze.db"
    shutil.copy2(DATA_DIR / "vault_maze.db", database)
    requests_path = dest / "release_requests.ndjson"
    shutil.copy2(DATA_DIR / "release_requests.ndjson", requests_path)
    output_dir = dest / "output"
    output_dir.mkdir(exist_ok=True)
    return {
        "root": dest,
        "runbooks": runbooks_dir,
        "release_config": release_config,
        "api_contract": api_contract,
        "database": database,
        "requests": requests_path,
        "output": output_dir / "release_report.json",
    }


@contextmanager
def new_workspace() -> Iterator[dict[str, Path]]:
    root = Path(tempfile.mkdtemp(prefix="vault-maze-lock-test-"))
    try:
        yield copy_fixture_tree(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def workspace() -> Iterator[dict[str, Path]]:
    with new_workspace() as paths:
        yield paths


# ---------------------------------------------------------------------------
# Candidate subprocess execution
# ---------------------------------------------------------------------------
def run_candidate(
    paths: dict[str, Path], timeout: float = 90.0
) -> subprocess.CompletedProcess:
    _require_binary()
    cmd = [
        str(BIN_PATH),
        "--runbooks",
        str(paths["runbooks"]),
        "--release-config",
        str(paths["release_config"]),
        "--api-contract",
        str(paths["api_contract"]),
        "--database",
        str(paths["database"]),
        "--requests",
        str(paths["requests"]),
        "--output",
        str(paths["output"]),
    ]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


def load_candidate_report(paths: dict[str, Path]) -> dict[str, Any]:
    with paths["output"].open("r", encoding="utf-8") as fh:
        return json.load(fh)


def assert_success(result: subprocess.CompletedProcess, paths: dict[str, Path]) -> None:
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    assert paths["output"].exists(), (
        "a successful run must produce the output report file"
    )


def assert_fatal(paths: dict[str, Path], result: subprocess.CompletedProcess) -> None:
    """Assert the candidate treated the input as an unrecoverable input error."""
    assert result.returncode != 0, (
        f"expected nonzero exit for malformed input, got 0\nstdout={result.stdout!r}"
    )
    assert result.stderr.strip(), "expected nonempty stderr on a fatal input error"
    assert not paths["output"].exists(), (
        "a fatal run must not leave an output file behind"
    )
    leftovers = list(paths["output"].parent.glob("*.tmp")) + list(
        paths["output"].parent.glob(paths["output"].name + ".*")
    )
    assert not leftovers, f"fatal run left temporary artifacts behind: {leftovers}"


def assert_detail_nullability(row: dict[str, Any]) -> None:
    details = row["details"]
    assert set(details.keys()) == DETAIL_KEYS, (
        f"details must contain exactly {DETAIL_KEYS}, got {set(details.keys())}"
    )


# ---------------------------------------------------------------------------
# Recursive report diffing (bounded to a handful of mismatches)
# ---------------------------------------------------------------------------
def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def diff_json(expected: Any, actual: Any, path: str = "$", limit: int = 8) -> list[str]:
    """Return up to ``limit`` recursive JSON differences with typed detail."""
    mismatches: list[str] = []

    def walk(exp: Any, act: Any, p: str) -> None:
        if len(mismatches) >= limit:
            return
        if isinstance(exp, dict) and isinstance(act, dict):
            exp_keys = set(exp)
            act_keys = set(act)
            missing = sorted(exp_keys - act_keys, key=lambda k: k.encode("utf-8"))
            extra = sorted(act_keys - exp_keys, key=lambda k: k.encode("utf-8"))
            for k in missing:
                if len(mismatches) >= limit:
                    return
                mismatches.append(
                    f"{p}.{k}: missing key expected_type={_json_type_name(exp[k])} "
                    f"expected_value={exp[k]!r} actual_type=missing actual_value=None"
                )
            for k in extra:
                if len(mismatches) >= limit:
                    return
                mismatches.append(
                    f"{p}.{k}: extra key expected_type=missing expected_value=None "
                    f"actual_type={_json_type_name(act[k])} actual_value={act[k]!r}"
                )
            for k in sorted(exp_keys & act_keys, key=lambda x: x.encode("utf-8")):
                if len(mismatches) >= limit:
                    return
                walk(exp[k], act[k], f"{p}.{k}")
        elif isinstance(exp, list) and isinstance(act, list):
            if len(exp) != len(act):
                mismatches.append(
                    f"{p}: array-length difference expected_type=array "
                    f"actual_type=array expected_length={len(exp)} "
                    f"actual_length={len(act)} expected_value=<omitted> "
                    f"actual_value=<omitted>"
                )
                return
            for i, (e, a) in enumerate(zip(exp, act)):
                if len(mismatches) >= limit:
                    return
                walk(e, a, f"{p}[{i}]")
        else:
            if exp != act:
                hint = ""
                if "runbook_id_or_null" in p or "step_id_or_null" in p:
                    hint = (
                        " (see report_schema.md § Rejection identity and detail matrix)"
                    )
                mismatches.append(
                    f"{p}: expected_type={_json_type_name(exp)} "
                    f"actual_type={_json_type_name(act)} "
                    f"expected_value={exp!r} actual_value={act!r}{hint}"
                )

    walk(expected, actual, path)
    return mismatches[:limit]


def load_golden_report() -> tuple[bytes, dict[str, Any]]:
    """Validate private golden fixture integrity via sidecar SHA-256."""
    golden_bytes = GOLDEN_PATH.read_bytes()
    digest = hashlib.sha256(golden_bytes).hexdigest()
    sidecar = GOLDEN_SHA256_PATH.read_text(encoding="utf-8").strip().lower()
    assert digest == sidecar, (
        "verifier-fixture error: golden SHA-256 does not match sidecar "
        f"(computed={digest} sidecar={sidecar})"
    )
    return golden_bytes, json.loads(golden_bytes.decode("utf-8"))


def candidate_pretty_json(report: dict[str, Any]) -> str:
    """Candidate-relative pretty serialization (2-space indent, one trailing LF)."""
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def rows_for(report: dict[str, Any], key: str, request_id: str) -> list[dict[str, Any]]:
    return [r for r in report[key] if r.get("request_id") == request_id]


def assert_caps_absent_from_execution_rows(
    report: dict[str, Any], request_id: str, capabilities: list[str]
) -> None:
    for step in rows_for(report, "step_rows", request_id):
        for cap in capabilities:
            assert cap not in step["required_capabilities"], (
                f"{cap} must not appear in step required_capabilities after "
                f"initial-applied subtraction"
            )
    for batch in rows_for(report, "batch_rows", request_id):
        for cap in capabilities:
            assert cap not in batch["required_capabilities"], (
                f"{cap} must not appear in batch required_capabilities after "
                f"initial-applied subtraction"
            )


# ---------------------------------------------------------------------------
# YAML runbook mutation helpers
# ---------------------------------------------------------------------------
def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True
        )


def write_synthetic_runbook(
    paths: dict[str, Path],
    runbook_id: str,
    *,
    requires: list[str] | None = None,
    conflicts: list[str] | None = None,
    replaces: list[str] | None = None,
    provides_runbook_ids: list[str] | None = None,
    plan_rank: int = 50,
    filename: str | None = None,
) -> None:
    """Write a minimal local-only runbook used by temporary deterministic cases."""
    raw: dict[str, Any] = {
        "runbook_id": runbook_id,
        "version": "1.0.0",
        "checksum_sha256": "0" * 64,
        "plan_rank": plan_rank,
        "requires": list(requires or []),
        "conflicts": list(conflicts or []),
        "replaces": list(replaces or []),
        "provides_runbook_ids": list(provides_runbook_ids or [runbook_id]),
        "allowed_api_revisions": ["api-v1", "api-v2"],
        "allowed_database_revisions": ["db-v1", "db-v2", "db-v3"],
        "steps": [
            {
                "step_id": f"{runbook_id}-s01",
                "step_rank": 10,
                "step_kind": "local_prepare",
                "requires_step_ids": [],
                "required_capabilities": [],
                "provided_capabilities": [],
                "api_operation_id_or_null": None,
                "http_method_or_null": None,
                "request_content_type_or_null": None,
                "accepted_statuses": [],
                "database_action_or_null": None,
                "retry_mode": "safe",
                "idempotency_key_source_or_null": None,
            }
        ],
    }
    raw["checksum_sha256"] = compute_runbook_checksum_from_raw(raw)
    out = paths["runbooks"] / (filename or f"{runbook_id}.yaml")
    dump_yaml(out, raw)


def run_candidate_bytes(paths: dict[str, Path], timeout: float = 90.0) -> bytes:
    """Run the candidate and return the raw report bytes."""
    result = run_candidate(paths, timeout=timeout)
    assert_success(result, paths)
    return paths["output"].read_bytes()


def assert_repeated_process_identity(
    paths: dict[str, Path],
    *,
    request_id: str,
    expected_reason: str,
    expected_runbook_id: str,
    expected_related_ids: list[str] | None = None,
    runs: int = 8,
) -> bytes:
    """Run the candidate in ``runs`` separate processes; require byte-identical reports."""
    reports: list[bytes] = []
    for _ in range(runs):
        if paths["output"].exists():
            paths["output"].unlink()
        for sibling in paths["output"].parent.glob("*"):
            if (
                sibling.name.startswith(paths["output"].name)
                and sibling != paths["output"]
            ):
                sibling.unlink()
        payload = run_candidate_bytes(paths)
        reports.append(payload)
        actual = json.loads(payload.decode("utf-8"))
        row = next(r for r in actual["rejection_rows"] if r["request_id"] == request_id)
        assert row["reason"] == expected_reason
        assert row["runbook_id_or_null"] == expected_runbook_id
        assert row["step_id_or_null"] is None
        if expected_related_ids is not None:
            assert row["details"]["related_ids"] == expected_related_ids
    assert len({r for r in reports}) == 1, (
        "identical inputs must produce byte-identical reports across separate processes"
    )
    return reports[0]


def runbook_path(paths: dict[str, Path], runbook_id: str) -> Path:
    return paths["runbooks"] / f"{runbook_id}.yaml"


def current_runbook_checksum(paths: dict[str, Path], runbook_id: str) -> str:
    raw = load_yaml(runbook_path(paths, runbook_id))
    return compute_runbook_checksum_from_raw(raw)


def mutate_runbook(
    paths: dict[str, Path],
    runbook_id: str,
    mutator: Callable[[dict[str, Any]], None],
    *,
    fix_checksum: bool = True,
) -> None:
    path = runbook_path(paths, runbook_id)
    raw = load_yaml(path)
    mutator(raw)
    if fix_checksum:
        raw["checksum_sha256"] = compute_runbook_checksum_from_raw(raw)
    dump_yaml(path, raw)


def corrupt_checksum(paths: dict[str, Path], runbook_id: str) -> None:
    path = runbook_path(paths, runbook_id)
    raw = load_yaml(path)
    old = raw["checksum_sha256"]
    raw["checksum_sha256"] = ("0" if old[0] != "0" else "1") + old[1:]
    dump_yaml(path, raw)


def duplicate_runbook_file(
    paths: dict[str, Path], runbook_id: str, new_filename: str
) -> None:
    src = runbook_path(paths, runbook_id)
    shutil.copy2(src, paths["runbooks"] / new_filename)


def find_step(raw: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in raw["steps"] if s["step_id"] == step_id)


# ---------------------------------------------------------------------------
# release.toml mutation helpers (no external TOML-writer dependency)
# ---------------------------------------------------------------------------
def load_release_profile_raw(paths: dict[str, Path]) -> dict[str, Any]:
    with paths["release_config"].open("rb") as fh:
        return tomllib.load(fh)


def dump_release_profile_raw(paths: dict[str, Path], profile: dict[str, Any]) -> None:
    def arr(values: list[str]) -> str:
        return "[" + ", ".join(f'"{v}"' for v in values) + "]"

    lines = [
        f'release_profile_version = "{profile["release_profile_version"]}"',
        f"maximum_runbooks_per_request = {profile['maximum_runbooks_per_request']}",
        f"maximum_steps_per_batch = {profile['maximum_steps_per_batch']}",
        f"supported_api_revisions = {arr(profile['supported_api_revisions'])}",
        f"supported_database_revisions = {arr(profile['supported_database_revisions'])}",
        f"allowed_retry_modes = {arr(profile['allowed_retry_modes'])}",
        f"allowed_execution_modes = {arr(profile['allowed_execution_modes'])}",
        f'required_checksum_algorithm = "{profile["required_checksum_algorithm"]}"',
        f'canonical_json_format = "{profile["canonical_json_format"]}"',
        "",
        "[replacement_preferences]",
    ]
    for k, v in profile.get("replacement_preferences", {}).items():
        lines.append(f'"{k}" = "{v}"')
    paths["release_config"].write_text("\n".join(lines) + "\n", encoding="utf-8")


def mutate_release_profile(
    paths: dict[str, Path], mutator: Callable[[dict[str, Any]], None]
) -> None:
    raw = load_release_profile_raw(paths)
    mutator(raw)
    dump_release_profile_raw(paths, raw)


def append_raw_toml_line(paths: dict[str, Path], line: str) -> None:
    """Insert a raw top-level TOML line before the first table header.

    Appending at end-of-file would land the line inside the last table
    (``[replacement_preferences]``), making it a nested key instead of an
    unknown top-level field.
    """
    text = paths["release_config"].read_text(encoding="utf-8")
    lines = text.splitlines()
    insert_at = len(lines)
    for idx, existing in enumerate(lines):
        if existing.strip().startswith("["):
            insert_at = idx
            break
    lines.insert(insert_at, line)
    paths["release_config"].write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# API contract mutation helpers
# ---------------------------------------------------------------------------
def load_contract(paths: dict[str, Path]) -> dict[str, Any]:
    return json.loads(paths["api_contract"].read_text(encoding="utf-8"))


def dump_contract(paths: dict[str, Path], data: dict[str, Any]) -> None:
    paths["api_contract"].write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def find_operation(
    data: dict[str, Any], api_revision: str, operation_id: str
) -> dict[str, Any]:
    return next(
        op
        for op in data["operations"]
        if op["api_revision"] == api_revision and op["operation_id"] == operation_id
    )


# ---------------------------------------------------------------------------
# NDJSON request helpers
# ---------------------------------------------------------------------------
def write_requests(paths: dict[str, Path], requests: list[dict[str, Any]]) -> None:
    with paths["requests"].open("w", encoding="utf-8") as fh:
        for req in requests:
            fh.write(json.dumps(req, separators=(",", ":")) + "\n")


def base_request(
    request_id: str,
    deployment_id: str,
    target_runbook_ids: list[str],
    target_api_revision: str = "api-v2",
    target_database_revision: str = "db-v2",
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "deployment_id": deployment_id,
        "target_runbook_ids": target_runbook_ids,
        "target_api_revision": target_api_revision,
        "target_database_revision": target_database_revision,
    }


# ---------------------------------------------------------------------------
# SQLite deployment registry helpers
# ---------------------------------------------------------------------------
def db_execute(db_path: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def db_executescript(db_path: Path, script: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def db_file_hash(db_path: Path) -> str:
    return hashlib.sha256(db_path.read_bytes()).hexdigest()


def insert_deployment(
    paths: dict[str, Path],
    deployment_id: str,
    database_revision: str,
    capabilities: list[str],
    applied_runbooks: dict[str, str] | None = None,
    capability_profile_version: str = "1",
) -> None:
    conn = sqlite3.connect(paths["database"])
    try:
        conn.execute(
            "INSERT INTO deployment_metadata VALUES (?, ?, ?)",
            (deployment_id, database_revision, capability_profile_version),
        )
        for cap in capabilities:
            conn.execute(
                "INSERT INTO database_capabilities VALUES (?, ?)", (deployment_id, cap)
            )
        for rb_id, checksum in (applied_runbooks or {}).items():
            conn.execute(
                "INSERT INTO applied_runbooks VALUES (?, ?, ?)",
                (deployment_id, rb_id, checksum),
            )
        conn.commit()
    finally:
        conn.close()


def add_capability(
    paths: dict[str, Path], deployment_id: str, capability_id: str
) -> None:
    db_execute(
        paths["database"],
        "INSERT OR IGNORE INTO database_capabilities VALUES (?, ?)",
        (deployment_id, capability_id),
    )


def remove_capability(
    paths: dict[str, Path], deployment_id: str, capability_id: str
) -> None:
    db_execute(
        paths["database"],
        "DELETE FROM database_capabilities WHERE deployment_id = ? AND capability_id = ?",
        (deployment_id, capability_id),
    )


def set_applied_checksum(
    paths: dict[str, Path], deployment_id: str, runbook_id: str, checksum: str
) -> None:
    db_execute(
        paths["database"],
        "INSERT INTO applied_runbooks VALUES (?, ?, ?) "
        "ON CONFLICT(deployment_id, runbook_id) DO UPDATE SET checksum_sha256 = excluded.checksum_sha256",
        (deployment_id, runbook_id, checksum),
    )


def clear_applied_runbooks(paths: dict[str, Path], deployment_id: str) -> None:
    db_execute(
        paths["database"],
        "DELETE FROM applied_runbooks WHERE deployment_id = ?",
        (deployment_id,),
    )


# ---------------------------------------------------------------------------
# Focused run helpers (no complete-report equality)
# ---------------------------------------------------------------------------
def expect_rejection(
    paths: dict[str, Path], request_id: str, expected_reason: str
) -> dict[str, Any]:
    """Run the candidate and assert `request_id` is rejected with `expected_reason`."""
    result = run_candidate(paths)
    assert_success(result, paths)
    actual = load_candidate_report(paths)

    act_row = next(r for r in actual["request_rows"] if r["request_id"] == request_id)
    assert act_row["status"] == "rejected"
    assert act_row["reason_or_null"] == expected_reason
    for key in (
        "selected_runbook_rows",
        "dependency_edge_rows",
        "step_rows",
        "batch_rows",
    ):
        assert rows_for(actual, key, request_id) == [], (
            f"rejected request {request_id} must not leave rows in {key}"
        )
    return actual


def expect_accepted(paths: dict[str, Path], request_id: str) -> dict[str, Any]:
    result = run_candidate(paths)
    assert_success(result, paths)
    actual = load_candidate_report(paths)
    act_row = next(r for r in actual["request_rows"] if r["request_id"] == request_id)
    assert act_row["status"] == "accepted"
    return actual


# ===========================================================================
# 1. Required files and malformed root inputs
# ===========================================================================
def test_01_required_files_and_malformed_root_inputs() -> None:
    """Every declared input artifact is required, and a syntactically
    malformed root document (YAML, TOML, JSON, or NDJSON) in any one of
    them must be treated as an unrecoverable input error: nonzero exit,
    nonempty stderr, no output file, and no leftover temp file."""
    with new_workspace() as paths:
        paths["release_config"].unlink()
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        with runbook_path(paths, "r01-bootstrap-session").open(
            "a", encoding="utf-8"
        ) as fh:
            fh.write("steps: [this is not: valid: yaml: [[[\n")
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        paths["release_config"].write_text(
            'release_profile_version = "1"\nmaximum_runbooks_per_request = [broken\n',
            encoding="utf-8",
        )
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        paths["api_contract"].write_text("{ this is not json ", encoding="utf-8")
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        with paths["requests"].open("a", encoding="utf-8") as fh:
            fh.write("{not valid json\n")
        result = run_candidate(paths)
        assert_fatal(paths, result)


# ===========================================================================
# 2. Duplicate identities and checksum integrity
# ===========================================================================
def test_02_duplicate_identities_and_checksum_integrity() -> None:
    """Duplicate runbook ids, duplicate step ids, duplicate API operation
    identities, duplicate request ids, and any runbook whose declared
    checksum does not match its recomputed canonical checksum (or is not
    syntactically a 64-character lowercase hex string) must all be
    unrecoverable input errors."""
    with new_workspace() as paths:
        duplicate_runbook_file(paths, "r01-bootstrap-session", "r01-duplicate.yaml")
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def add_dup_step(raw: dict[str, Any]) -> None:
            raw["steps"].append(dict(raw["steps"][0]))

        mutate_runbook(paths, "r01-bootstrap-session", add_dup_step, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        contract["operations"].append(dict(contract["operations"][0]))
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        raw_lines = paths["requests"].read_text(encoding="utf-8").splitlines()
        first = json.loads(raw_lines[0])
        with paths["requests"].open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(first, separators=(",", ":")) + "\n")
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        corrupt_checksum(paths, "r02-authenticate-vault")
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def bad_syntax(raw: dict[str, Any]) -> None:
            raw["checksum_sha256"] = "not-a-valid-hex-checksum"

        mutate_runbook(paths, "r03-enter-maze", bad_syntax, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)


# ===========================================================================
# 3. Bounded YAML and TOML schemas
# ===========================================================================
def test_03_bounded_yaml_and_toml_schemas() -> None:
    """The runbook YAML schema and the release-profile TOML schema are both
    closed: unknown top-level fields, unknown step fields, invalid
    step-kind/retry-mode tokens, an invalid combination of API-only fields
    on a non-API step, an empty step list, and duplicate entries inside a
    logically-unique array must all be rejected as fatal."""
    with new_workspace() as paths:

        def add_unknown(raw: dict[str, Any]) -> None:
            raw["totally_unknown_field"] = "x"

        mutate_runbook(paths, "r04-read-clue", add_unknown, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def add_unknown_step_field(raw: dict[str, Any]) -> None:
            find_step(raw, "r04-s01-prep")["totally_unknown"] = "x"

        mutate_runbook(
            paths, "r04-read-clue", add_unknown_step_field, fix_checksum=False
        )
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def bad_kind(raw: dict[str, Any]) -> None:
            find_step(raw, "r04-s01-prep")["step_kind"] = "not_a_real_kind"

        mutate_runbook(paths, "r04-read-clue", bad_kind, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def bad_retry(raw: dict[str, Any]) -> None:
            find_step(raw, "r04-s01-prep")["retry_mode"] = "sometimes"

        mutate_runbook(paths, "r04-read-clue", bad_retry, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def api_fields_on_local(raw: dict[str, Any]) -> None:
            find_step(raw, "r04-s01-prep")["http_method_or_null"] = "GET"

        mutate_runbook(paths, "r04-read-clue", api_fields_on_local, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def empty_steps(raw: dict[str, Any]) -> None:
            raw["steps"] = []

        mutate_runbook(paths, "r04-read-clue", empty_steps, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:

        def dup_requires(raw: dict[str, Any]) -> None:
            raw["requires"] = (
                list(raw["requires"]) * 2 if raw["requires"] else ["x", "x"]
            )

        mutate_runbook(paths, "r05-commit-clue", dup_requires, fix_checksum=False)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        append_raw_toml_line(paths, 'totally_unknown_toml_field = "x"')
        result = run_candidate(paths)
        assert_fatal(paths, result)


# ===========================================================================
# 4. Normalized API contract schema
# ===========================================================================
def test_04_normalized_api_contract_schema() -> None:
    """The Flask API contract schema is closed and normalized: unknown
    top-level or per-operation fields, a duplicate content type within one
    operation, an unparsable HTTP method token, a media type with
    parameters, and a success-status list that is empty or out of the
    2xx range must all be fatal."""
    with new_workspace() as paths:
        contract = load_contract(paths)
        contract["totally_unknown"] = True
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        find_operation(contract, "api-v2", "op-auth-vault")["totally_unknown"] = "x"
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        op = find_operation(contract, "api-v2", "op-auth-vault")
        op["accepted_request_content_types"] = ["application/json", "application/json"]
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        find_operation(contract, "api-v2", "op-auth-vault")["method"] = "12345"
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        op = find_operation(contract, "api-v2", "op-auth-vault")
        op["accepted_request_content_types"] = ["application/json; charset=utf-8"]
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        find_operation(contract, "api-v2", "op-auth-vault")["success_statuses"] = []
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        contract = load_contract(paths)
        find_operation(contract, "api-v2", "op-auth-vault")["success_statuses"] = [404]
        dump_contract(paths, contract)
        result = run_candidate(paths)
        assert_fatal(paths, result)


# ===========================================================================
# 5. SQLite deployment registry and read-only access
# ===========================================================================
def test_05_sqlite_deployment_registry_and_readonly() -> None:
    """The SQLite deployment registry must expose exactly the three
    expected tables, must never contain a capability or applied-runbook
    row referencing an unknown deployment, must reject a syntactically
    invalid stored checksum, and a successful candidate run must leave
    the database file byte-for-byte unchanged (opened read-only, never
    written to)."""
    with new_workspace() as paths:
        before_hash = db_file_hash(paths["database"])
        write_requests(
            paths,
            [
                base_request(
                    "req-readonly",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        expect_accepted(paths, "req-readonly")
        after_hash = db_file_hash(paths["database"])
        assert before_hash == after_hash, (
            "the candidate must not mutate the SQLite deployment registry"
        )
        conn = sqlite3.connect(f"file:{paths['database']}?mode=ro", uri=True)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT INTO database_capabilities VALUES (?, ?)",
                    ("deployment-staging-v2", "probe:capability"),
                )
        finally:
            conn.close()

    with new_workspace() as paths:
        db_executescript(paths["database"], "DROP TABLE database_capabilities;")
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        db_execute(
            paths["database"],
            "INSERT INTO database_capabilities VALUES (?, ?)",
            ("deployment-does-not-exist", "some:capability"),
        )
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        db_execute(
            paths["database"],
            "INSERT INTO applied_runbooks VALUES (?, ?, ?)",
            ("deployment-does-not-exist", "r01-bootstrap-session", "a" * 64),
        )
        result = run_candidate(paths)
        assert_fatal(paths, result)

    with new_workspace() as paths:
        db_execute(
            paths["database"],
            "UPDATE applied_runbooks SET checksum_sha256 = ? "
            "WHERE deployment_id = ? AND runbook_id = ?",
            ("not-hex", "deployment-staging-v2", "r01-bootstrap-session"),
        )
        result = run_candidate(paths)
        assert_fatal(paths, result)


# ===========================================================================
# 6. Direct runbook dependency
# ===========================================================================
def test_06_direct_runbook_dependency() -> None:
    """A request targeting a runbook with exactly one direct dependency
    must select both, mark the already-applied dependency as
    non-executable with a null topological position, and execute only the
    directly requested runbook."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-direct", "deployment-staging-v2", ["r02-authenticate-vault"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-direct")
        selected = {
            r["runbook_id"]: r
            for r in rows_for(actual, "selected_runbook_rows", "req-direct")
        }
        assert set(selected) == {"r01-bootstrap-session", "r02-authenticate-vault"}
        assert selected["r01-bootstrap-session"]["already_applied"] is True
        assert selected["r01-bootstrap-session"]["executable"] is False
        assert selected["r01-bootstrap-session"]["topological_position_or_null"] is None
        assert selected["r02-authenticate-vault"]["selection_reason"] == "requested"
        assert selected["r02-authenticate-vault"]["executable"] is True
        step_runbooks = {
            s["runbook_id"] for s in rows_for(actual, "step_rows", "req-direct")
        }
        assert step_runbooks == {"r02-authenticate-vault"}

    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-direct-r07",
                    "deployment-staging-v2",
                    ["r07-legacy-clue-sync"],
                    target_api_revision="api-v1",
                )
            ],
        )
        actual = expect_accepted(paths, "req-direct-r07")
        selected = {
            r["runbook_id"]: r
            for r in rows_for(actual, "selected_runbook_rows", "req-direct-r07")
        }
        assert "r07-legacy-clue-sync" in selected
        assert selected["r07-legacy-clue-sync"]["selection_reason"] == "requested"
        assert "r08-safe-clue-sync" not in selected
        assert not any(
            e["edge_type"] == "replacement_provides"
            and e["to_runbook_id"] == "r07-legacy-clue-sync"
            for e in rows_for(actual, "dependency_edge_rows", "req-direct-r07")
        )


# ===========================================================================
# 7. Transitive dependency closure
# ===========================================================================
def test_07_transitive_dependency_closure() -> None:
    """A request targeting a deeply-nested runbook must pull in the full
    transitive closure of `requires` edges, including dependency-only
    replacement of r07 by r08, and record a replacement_provides edge."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-transitive", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-transitive")
        selected_ids = {
            r["runbook_id"]
            for r in rows_for(actual, "selected_runbook_rows", "req-transitive")
        }
        assert selected_ids == {
            "r01-bootstrap-session",
            "r02-authenticate-vault",
            "r03-enter-maze",
            "r04-read-clue",
            "r05-commit-clue",
            "r06-unlock-route",
            "r08-safe-clue-sync",
        }
        edges = rows_for(actual, "dependency_edge_rows", "req-transitive")
        assert any(e["edge_type"] == "replacement_provides" for e in edges), (
            "transitive closure must record replacement_provides for r08→r07"
        )


# ===========================================================================
# 8. Missing dependency
# ===========================================================================
def test_08_missing_dependency() -> None:
    """If a runbook's declared dependency does not exist anywhere in the
    runbooks directory, any request whose closure needs that dependency
    must be rejected with `missing_dependency`, identifying the missing
    id, before any other stage of validation runs."""
    with new_workspace() as paths:
        runbook_path(paths, "r01-bootstrap-session").unlink()
        write_requests(
            paths,
            [
                base_request(
                    "req-missing-dep",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-missing-dep", "missing_dependency")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-missing-dep"
        )
        # runbook_id_or_null identifies the missing dependency, not the requester.
        assert row["runbook_id_or_null"] == "r01-bootstrap-session"
        assert row["step_id_or_null"] is None
        assert row["details"]["related_ids"] == []

    # Multiple reachable requesters / missing edges: canonical identity is stable
    # across reversed file creation order, reversed requires-array order, and
    # separate candidate processes.
    with new_workspace() as paths:
        # Create beta before alpha (physical creation order reversed vs UTF-8 ids).
        write_synthetic_runbook(
            paths,
            "syn-beta",
            requires=["missing-alpha"],
        )
        write_synthetic_runbook(
            paths,
            "syn-alpha",
            # requires-array lists a known dep before the missing one; reversed
            # below must not change the selected missing identity.
            requires=["r01-bootstrap-session", "missing-zeta"],
        )
        mutate_runbook(
            paths,
            "syn-alpha",
            lambda raw: raw.__setitem__(
                "requires", ["missing-zeta", "r01-bootstrap-session"]
            ),
        )
        write_requests(
            paths,
            [
                base_request(
                    "req-multi-missing",
                    "deployment-staging-v2",
                    ["syn-beta", "syn-alpha"],
                )
            ],
        )
        assert_repeated_process_identity(
            paths,
            request_id="req-multi-missing",
            expected_reason="missing_dependency",
            expected_runbook_id="missing-zeta",
            expected_related_ids=[],
            runs=8,
        )


# ===========================================================================
# 9. Deterministic runbook cycle reporting
# ===========================================================================
def test_09_deterministic_runbook_cycle_reporting() -> None:
    """A dependency cycle introduced between two runbooks must be
    rejected with `dependency_cycle`, and the reported cycle members must
    be deterministic (sorted by UTF-8 byte order) rather than depend on
    filesystem or dict iteration order."""
    with new_workspace() as paths:

        def add_cycle_edge(raw: dict[str, Any]) -> None:
            raw["requires"] = [*list(raw["requires"]), "r06-unlock-route"]

        mutate_runbook(paths, "r07-legacy-clue-sync", add_cycle_edge)
        write_requests(
            paths,
            [base_request("req-cycle", "deployment-staging-v2", ["r06-unlock-route"])],
        )
        actual = expect_rejection(paths, "req-cycle", "dependency_cycle")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-cycle"
        )
        members = row["details"]["cycle_members"]
        assert members == sorted(members), (
            "cycle members must be reported in UTF-8 sorted order"
        )
        assert set(members).issubset(
            {"r05-commit-clue", "r06-unlock-route", "r07-legacy-clue-sync"}
        )
        assert len(members) >= 2


# ===========================================================================
# 10. Effective conflict behavior
# ===========================================================================
def test_10_effective_conflict_behavior() -> None:
    """Two runbooks that declare each other as conflicting must reject the
    request with `selected_runbook_conflict` when both are directly
    targeted (bypassing replacement), but must succeed once only the
    replacement-preferred runbook is effectively selected."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-conflict",
                    "deployment-staging-v2",
                    ["r06-unlock-route", "r07-legacy-clue-sync"],
                )
            ],
        )
        expect_rejection(paths, "req-conflict", "selected_runbook_conflict")

    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-no-conflict", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        expect_accepted(paths, "req-no-conflict")


# ===========================================================================
# 11. Valid preferred replacement
# ===========================================================================
def test_11_valid_preferred_replacement() -> None:
    """When a non-direct-target runbook has a configured replacement, the
    replacement must be substituted end to end: it appears in
    selected_runbook_rows with `selection_reason = replacement` and lists
    the id it replaces, a `replacement_provides` dependency edge is
    recorded, and the replaced runbook does not appear anywhere in the
    report for that request."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-replace", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-replace")
        selected = {
            r["runbook_id"]: r
            for r in rows_for(actual, "selected_runbook_rows", "req-replace")
        }
        assert "r07-legacy-clue-sync" not in selected
        assert selected["r08-safe-clue-sync"]["selection_reason"] == "replacement"
        assert selected["r08-safe-clue-sync"]["replaces_runbook_ids"] == [
            "r07-legacy-clue-sync"
        ]
        edges = rows_for(actual, "dependency_edge_rows", "req-replace")
        replacement_edges = [
            e for e in edges if e["edge_type"] == "replacement_provides"
        ]
        assert any(
            e["to_runbook_id"] == "r07-legacy-clue-sync"
            and e["satisfied_by_runbook_id"] == "r08-safe-clue-sync"
            for e in replacement_edges
        )
        # topological_position is UTF-8 enumeration of executable IDs, not
        # schedule order; replacement provenance does not invent positions.
        executable_ids = sorted(
            (rid for rid, row in selected.items() if row["executable"]),
            key=lambda rid: rid.encode("utf-8"),
        )
        for index, rid in enumerate(executable_ids, start=1):
            assert selected[rid]["topological_position_or_null"] == index
        steps = sorted(
            rows_for(actual, "step_rows", "req-replace"),
            key=lambda s: s["global_step_position"],
        )
        first_r08 = next(
            i for i, s in enumerate(steps) if s["runbook_id"] == "r08-safe-clue-sync"
        )
        first_r05 = next(
            i for i, s in enumerate(steps) if s["runbook_id"] == "r05-commit-clue"
        )
        assert first_r08 < first_r05
        assert (
            selected["r08-safe-clue-sync"]["topological_position_or_null"]
            > selected["r05-commit-clue"]["topological_position_or_null"]
        )


# ===========================================================================
# 12. Replacement unsatisfied
# ===========================================================================
def test_12_replacement_unsatisfied() -> None:
    """If the configured replacement preference points at a runbook id
    that does not exist, any request whose closure needs the replaced
    runbook must be rejected with `replacement_unsatisfied`."""
    with new_workspace() as paths:

        def break_replacement(raw: dict[str, Any]) -> None:
            raw["replacement_preferences"] = {
                "r07-legacy-clue-sync": "does-not-exist-anywhere"
            }

        mutate_release_profile(paths, break_replacement)
        write_requests(
            paths,
            [
                base_request(
                    "req-repl-broken", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        expect_rejection(paths, "req-repl-broken", "replacement_unsatisfied")

    # Two applicable unsatisfied pairs: identity follows canonical (old_id, new_id)
    # order, not physical TOML table order, and is stable across processes.
    def install_two_unsatisfied_pairs(
        paths: dict[str, Path], *, toml_order: list[tuple[str, str]]
    ) -> None:
        write_synthetic_runbook(paths, "old-z")
        write_synthetic_runbook(paths, "old-a")
        write_synthetic_runbook(
            paths,
            "dep-anchor",
            requires=["old-z", "old-a"],
        )

        def set_prefs(raw: dict[str, Any]) -> None:
            raw["replacement_preferences"] = {
                old_id: new_id for old_id, new_id in toml_order
            }

        mutate_release_profile(paths, set_prefs)
        write_requests(
            paths,
            [
                base_request(
                    "req-multi-repl",
                    "deployment-staging-v2",
                    ["dep-anchor"],
                )
            ],
        )

    for toml_order in (
        [("old-z", "new-z-missing"), ("old-a", "new-a-missing")],
        [("old-a", "new-a-missing"), ("old-z", "new-z-missing")],
    ):
        with new_workspace() as paths:
            install_two_unsatisfied_pairs(paths, toml_order=list(toml_order))
            assert_repeated_process_identity(
                paths,
                request_id="req-multi-repl",
                expected_reason="replacement_unsatisfied",
                expected_runbook_id="old-a",
                expected_related_ids=["old-a", "new-a-missing"],
                runs=8,
            )


# ===========================================================================
# 13. Applied checksum match
# ===========================================================================
def test_13_applied_checksum_match() -> None:
    """A dependency that is already applied in the deployment registry
    with a matching checksum must be reported as matched/already-applied/
    non-executable with a null topological position, and must not appear
    in step_rows or batch_rows for the request - only the newly-executed
    runbooks appear there."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-matched", "deployment-staging-v2", ["r02-authenticate-vault"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-matched")
        selected = {
            r["runbook_id"]: r
            for r in rows_for(actual, "selected_runbook_rows", "req-matched")
        }
        r01 = selected["r01-bootstrap-session"]
        assert r01["checksum_status"] == "matched"
        assert r01["already_applied"] is True
        assert r01["executable"] is False
        assert r01["topological_position_or_null"] is None
        step_rbs = {
            s["runbook_id"] for s in rows_for(actual, "step_rows", "req-matched")
        }
        batch_rbs = {
            rb
            for b in rows_for(actual, "batch_rows", "req-matched")
            for rb in b["runbook_ids"]
        }
        assert "r01-bootstrap-session" not in step_rbs
        assert "r01-bootstrap-session" not in batch_rbs
        for step in rows_for(actual, "step_rows", "req-matched"):
            if step["runbook_id"] == "r02-authenticate-vault":
                assert (
                    "state:vault_session_ready" not in step["required_capabilities"]
                ), "initial applied capability must be subtracted from r02 steps"


# ===========================================================================
# 14. Applied checksum drift
# ===========================================================================
def test_14_applied_checksum_drift() -> None:
    """Whenever the checksum recorded in the deployment registry for an
    applied runbook no longer matches that runbook's current canonical
    checksum, the request must be rejected with `applied_checksum_drift`
    naming the drifted runbook - even for a deployment that is not one of
    the checked-in drift fixtures."""
    with new_workspace() as paths:
        drifted_checksum = "f" * 64
        assert drifted_checksum != current_runbook_checksum(
            paths, "r01-bootstrap-session"
        )
        set_applied_checksum(
            paths, "deployment-staging-v2", "r01-bootstrap-session", drifted_checksum
        )
        write_requests(
            paths,
            [
                base_request(
                    "req-drift", "deployment-staging-v2", ["r02-authenticate-vault"]
                )
            ],
        )
        actual = expect_rejection(paths, "req-drift", "applied_checksum_drift")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-drift"
        )
        assert row["runbook_id_or_null"] == "r01-bootstrap-session"
        assert row["step_id_or_null"] is None
        assert_detail_nullability(row)
        assert row["details"]["actual_or_null"] is None
        assert row["details"]["expected_or_null"] is None


# ===========================================================================
# 15. API revision and operation existence
# ===========================================================================
def test_15_api_revision_and_operation_existence() -> None:
    """A target API revision unsupported by the release profile, a
    selected runbook that forbids the target API revision, and a runbook
    step referencing an API operation that does not exist for the target
    revision must each be rejected with their own distinct reason:
    `unknown_api_revision`, `runbook_api_revision_forbidden`, and
    `unknown_api_operation` respectively."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-unknown-rev",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                    target_api_revision="api-v9",
                )
            ],
        )
        actual = expect_rejection(paths, "req-unknown-rev", "unknown_api_revision")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-unknown-rev"
        )
        assert row["runbook_id_or_null"] is None
        assert row["step_id_or_null"] is None
        assert_detail_nullability(row)

    with new_workspace() as paths:

        def forbid_api_v2(raw: dict[str, Any]) -> None:
            raw["allowed_api_revisions"] = ["api-v1"]

        mutate_runbook(paths, "r02-authenticate-vault", forbid_api_v2)
        write_requests(
            paths,
            [
                base_request(
                    "req-forbidden-rev",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-forbidden-rev", "runbook_api_revision_forbidden"
        )
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-forbidden-rev"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] is None
        assert_detail_nullability(row)

    with new_workspace() as paths:
        contract = load_contract(paths)
        contract["operations"] = [
            op
            for op in contract["operations"]
            if not (
                op["api_revision"] == "api-v2" and op["operation_id"] == "op-auth-vault"
            )
        ]
        dump_contract(paths, contract)
        write_requests(
            paths,
            [
                base_request(
                    "req-unknown-op",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-unknown-op", "unknown_api_operation")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-unknown-op"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"
        assert_detail_nullability(row)

    # Multi-failure: unknown API operation outranks database_revision_mismatch.
    with new_workspace() as paths:
        contract = load_contract(paths)
        contract["operations"] = [
            op
            for op in contract["operations"]
            if not (
                op["api_revision"] == "api-v2" and op["operation_id"] == "op-auth-vault"
            )
        ]
        dump_contract(paths, contract)
        write_requests(
            paths,
            [
                base_request(
                    "req-api-over-db",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                    target_database_revision="db-v9",
                )
            ],
        )
        actual = expect_rejection(paths, "req-api-over-db", "unknown_api_operation")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-api-over-db"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"


# ===========================================================================
# 16. API method compatibility
# ===========================================================================
def test_16_api_method_compatibility() -> None:
    """A step whose declared HTTP method disagrees with the contract's
    method for that operation and revision must be rejected with
    `api_method_mismatch`, reporting both the expected and actual method -
    verified against the checked-in fixture case and against an
    independently constructed mismatch."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-method-fixture",
                    "deployment-staging-v2",
                    ["r06-unlock-route"],
                    target_api_revision="api-v1",
                )
            ],
        )
        actual = expect_rejection(paths, "req-method-fixture", "api_method_mismatch")
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-method-fixture"
        )
        assert row["details"]["expected_or_null"] == "POST"
        assert row["details"]["actual_or_null"] == "PATCH"
        assert row["runbook_id_or_null"] == "r06-unlock-route"
        assert row["step_id_or_null"] == "r06-s02-unlock"

    with new_workspace() as paths:

        def swap_method(raw: dict[str, Any]) -> None:
            find_step(raw, "r02-s02-auth")["http_method_or_null"] = "PUT"

        mutate_runbook(paths, "r02-authenticate-vault", swap_method)
        write_requests(
            paths,
            [
                base_request(
                    "req-method-synth",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-method-synth", "api_method_mismatch")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-method-synth"
        )
        assert row["details"]["expected_or_null"] == "POST"
        assert row["details"]["actual_or_null"] == "PUT"
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"

    # Multi-failure: api_method_mismatch outranks invalid_step_dependency.
    with new_workspace() as paths:

        def dangling_on_r04(raw: dict[str, Any]) -> None:
            find_step(raw, "r04-s02-read")["requires_step_ids"] = [
                "does-not-exist-in-runbook"
            ]

        mutate_runbook(paths, "r04-read-clue", dangling_on_r04)
        write_requests(
            paths,
            [
                base_request(
                    "req-method-over-step",
                    "deployment-staging-v2",
                    ["r06-unlock-route"],
                    target_api_revision="api-v1",
                )
            ],
        )
        actual = expect_rejection(paths, "req-method-over-step", "api_method_mismatch")
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-method-over-step"
        )
        assert row["runbook_id_or_null"] == "r06-unlock-route"
        assert row["step_id_or_null"] == "r06-s02-unlock"


# ===========================================================================
# 17. Content type and accepted status compatibility
# ===========================================================================
def test_17_content_type_and_accepted_status_compatibility() -> None:
    """A step whose request content type is not among the operation's
    accepted content types must be rejected with
    `api_content_type_mismatch`, a step whose accepted_statuses is not a
    subset of the operation's success_statuses must be rejected with
    `api_success_status_mismatch` independently of each other, and content
    type comparison must be case-insensitive rather than an exact byte
    match."""
    with new_workspace() as paths:

        def bad_content_type(raw: dict[str, Any]) -> None:
            find_step(raw, "r02-s02-auth")["request_content_type_or_null"] = (
                "text/plain"
            )

        mutate_runbook(paths, "r02-authenticate-vault", bad_content_type)
        write_requests(
            paths,
            [
                base_request(
                    "req-ct-mismatch",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-ct-mismatch", "api_content_type_mismatch")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-ct-mismatch"
        )
        assert_detail_nullability(row)
        assert row["details"]["actual_or_null"] is None
        assert row["details"]["expected_or_null"] is None
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"

    with new_workspace() as paths:
        # A differently-cased but otherwise identical content type must
        # still be treated as compatible - this fails for a candidate that
        # compares content types byte-for-byte instead of normalizing case.
        def uppercase_content_type(raw: dict[str, Any]) -> None:
            step = find_step(raw, "r02-s02-auth")
            step["request_content_type_or_null"] = step[
                "request_content_type_or_null"
            ].upper()

        mutate_runbook(paths, "r02-authenticate-vault", uppercase_content_type)
        write_requests(
            paths,
            [
                base_request(
                    "req-ct-case-insensitive",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        expect_accepted(paths, "req-ct-case-insensitive")

    with new_workspace() as paths:

        def widen_statuses(raw: dict[str, Any]) -> None:
            find_step(raw, "r02-s02-auth")["accepted_statuses"] = [200, 299]

        mutate_runbook(paths, "r02-authenticate-vault", widen_statuses)
        write_requests(
            paths,
            [
                base_request(
                    "req-status-mismatch",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-status-mismatch", "api_success_status_mismatch"
        )
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-status-mismatch"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"


# ===========================================================================
# 18. Database deployment and revision compatibility
# ===========================================================================
def test_18_database_deployment_and_revision_compatibility() -> None:
    """A target database revision unsupported by the release profile, a
    target database revision that disagrees with the deployment's actual
    recorded revision, and a selected runbook that forbids the target
    database revision must each be rejected with the correct reason.
    For ``database_revision_mismatch``, both ``expected_or_null`` and
    ``actual_or_null`` remain null in rejection details."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-unsupported-db",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                    target_database_revision="db-v9",
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-unsupported-db", "database_revision_mismatch"
        )
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-unsupported-db"
        )
        assert row["details"]["expected_or_null"] is None
        assert row["details"]["actual_or_null"] is None
        assert row["runbook_id_or_null"] is None
        assert row["step_id_or_null"] is None
        assert_detail_nullability(row)

    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-db-actual-mismatch",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                    target_database_revision="db-v1",
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-db-actual-mismatch", "database_revision_mismatch"
        )
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-db-actual-mismatch"
        )
        assert row["details"]["expected_or_null"] is None
        assert row["details"]["actual_or_null"] is None
        assert row["runbook_id_or_null"] is None
        assert row["step_id_or_null"] is None
        assert_detail_nullability(row)

    with new_workspace() as paths:

        def forbid_db_v2(raw: dict[str, Any]) -> None:
            raw["allowed_database_revisions"] = ["db-v1", "db-v3"]

        mutate_runbook(paths, "r02-authenticate-vault", forbid_db_v2)
        write_requests(
            paths,
            [
                base_request(
                    "req-db-forbidden",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-db-forbidden", "runbook_database_revision_forbidden"
        )
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-db-forbidden"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] is None
        assert_detail_nullability(row)

    # Multi-failure: runbook_api_revision_forbidden outranks database mismatch.
    with new_workspace() as paths:

        def forbid_api_v2(raw: dict[str, Any]) -> None:
            raw["allowed_api_revisions"] = ["api-v1"]

        mutate_runbook(paths, "r02-authenticate-vault", forbid_api_v2)
        write_requests(
            paths,
            [
                base_request(
                    "req-api-forbid-over-db",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                    target_database_revision="db-v1",
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-api-forbid-over-db", "runbook_api_revision_forbidden"
        )
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-api-forbid-over-db"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] is None


# ===========================================================================
# 19. Initial and applied capabilities
# ===========================================================================
def test_19_initial_and_applied_capabilities() -> None:
    """A capability provided by an already-applied (matching-checksum)
    runbook must be available immediately, without that runbook appearing
    in step_rows/batch_rows; the same capability, when the providing
    runbook has not been applied at all, must instead be produced by that
    runbook executing as part of the plan."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-initial-cap",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_accepted(paths, "req-initial-cap")
        step_rbs = {
            s["runbook_id"] for s in rows_for(actual, "step_rows", "req-initial-cap")
        }
        assert step_rbs == {"r02-authenticate-vault"}
        assert_caps_absent_from_execution_rows(
            actual, "req-initial-cap", ["state:vault_session_ready"]
        )

    with new_workspace() as paths:
        clear_applied_runbooks(paths, "deployment-staging-v2")
        write_requests(
            paths,
            [
                base_request(
                    "req-applied-cap",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_accepted(paths, "req-applied-cap")
        step_rbs = {
            s["runbook_id"] for s in rows_for(actual, "step_rows", "req-applied-cap")
        }
        assert step_rbs == {"r01-bootstrap-session", "r02-authenticate-vault"}
        steps = sorted(
            rows_for(actual, "step_rows", "req-applied-cap"),
            key=lambda s: s["global_step_position"],
        )
        r01_positions = [
            s["global_step_position"]
            for s in steps
            if s["runbook_id"] == "r01-bootstrap-session"
        ]
        r02_positions = [
            s["global_step_position"]
            for s in steps
            if s["runbook_id"] == "r02-authenticate-vault"
        ]
        assert max(r01_positions) < min(r02_positions), (
            "the capability producer must execute strictly before its consumer"
        )


# ===========================================================================
# 20. Capability producer ordering
# ===========================================================================
def test_20_capability_producer_ordering() -> None:
    """A required capability that no selected or already-applied runbook
    ever provides must be rejected with `missing_database_capability`
    naming the missing capability; and when a capability is genuinely
    produced earlier in the plan, the candidate must place the producer's
    batch strictly before the consumer's batch rather than merging or
    reordering them."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-missing-cap",
                    "deployment-audit-v3",
                    ["r09-audit-terminal"],
                    target_database_revision="db-v3",
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-missing-cap", "missing_database_capability"
        )
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-missing-cap"
        )
        assert row["details"]["related_ids"] == ["db:table:audit_events"]
        assert row["runbook_id_or_null"] == "r09-audit-terminal"
        assert row["step_id_or_null"] == "r09-s01-prep"

    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-producer-order", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-producer-order")
        batches = sorted(
            rows_for(actual, "batch_rows", "req-producer-order"),
            key=lambda b: b["batch_index"],
        )
        # Use a capability that is produced in-plan and is NOT part of the
        # initial applied set, so it remains in projected required_capabilities.
        producer_index = next(
            b["batch_index"]
            for b in batches
            if "state:legacy_sync_ready" in b["produced_capabilities"]
        )
        consumer_index = next(
            b["batch_index"]
            for b in batches
            if "state:legacy_sync_ready" in b["required_capabilities"]
        )
        assert producer_index < consumer_index
        # Remaining-requirement projection: initial-applied caps stay absent.
        initial_like = {"db:column:maze_clues.route_token", "state:vault_session_ready"}
        for batch in batches:
            for cap in batch["required_capabilities"]:
                assert cap not in initial_like
        edges = rows_for(actual, "dependency_edge_rows", "req-producer-order")
        assert any(
            e["edge_type"] in ("requires", "replacement_provides") for e in edges
        )

    # Multi-failure: missing_database_capability outranks invalid_retry_policy.
    with new_workspace() as paths:

        def bad_audit_write_retry(raw: dict[str, Any]) -> None:
            find_step(raw, "r09-s03-write")["retry_mode"] = "safe"

        mutate_runbook(paths, "r09-audit-terminal", bad_audit_write_retry)
        write_requests(
            paths,
            [
                base_request(
                    "req-cap-over-retry",
                    "deployment-audit-v3",
                    ["r09-audit-terminal"],
                    target_database_revision="db-v3",
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-cap-over-retry", "missing_database_capability"
        )
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-cap-over-retry"
        )
        assert row["runbook_id_or_null"] == "r09-audit-terminal"
        assert row["step_id_or_null"] == "r09-s01-prep"


# ===========================================================================
# 21. Local step dependency validation
# ===========================================================================
def test_21_local_step_dependency_validation() -> None:
    """A step that requires itself, a step that requires a step id that
    does not exist anywhere in its own runbook, and a two-step cycle
    within a single runbook's steps must all be rejected with
    `invalid_step_dependency`."""
    with new_workspace() as paths:

        def self_loop(raw: dict[str, Any]) -> None:
            step = find_step(raw, "r04-s01-prep")
            step["requires_step_ids"] = [step["step_id"]]

        mutate_runbook(paths, "r04-read-clue", self_loop)
        write_requests(
            paths,
            [base_request("req-self-loop", "deployment-staging-v2", ["r04-read-clue"])],
        )
        actual = expect_rejection(paths, "req-self-loop", "invalid_step_dependency")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-self-loop"
        )
        assert row["runbook_id_or_null"] == "r04-read-clue"
        assert row["step_id_or_null"] == "r04-s01-prep"

    with new_workspace() as paths:

        def dangling_dep(raw: dict[str, Any]) -> None:
            find_step(raw, "r04-s02-read")["requires_step_ids"] = [
                "does-not-exist-in-runbook"
            ]

        mutate_runbook(paths, "r04-read-clue", dangling_dep)
        write_requests(
            paths,
            [
                base_request(
                    "req-dangling-dep", "deployment-staging-v2", ["r04-read-clue"]
                )
            ],
        )
        actual = expect_rejection(paths, "req-dangling-dep", "invalid_step_dependency")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-dangling-dep"
        )
        assert row["runbook_id_or_null"] == "r04-read-clue"
        assert row["step_id_or_null"] == "r04-s02-read"

    with new_workspace() as paths:

        def two_step_cycle(raw: dict[str, Any]) -> None:
            find_step(raw, "r05-s01-verify")["requires_step_ids"] = ["r05-s02-commit"]

        mutate_runbook(paths, "r05-commit-clue", two_step_cycle)
        write_requests(
            paths,
            [
                base_request(
                    "req-step-cycle", "deployment-staging-v2", ["r05-commit-clue"]
                )
            ],
        )
        actual = expect_rejection(paths, "req-step-cycle", "invalid_step_dependency")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-step-cycle"
        )
        assert row["runbook_id_or_null"] == "r05-commit-clue"
        assert row["step_id_or_null"] is None


# ===========================================================================
# 22. Retry and idempotency rules
# ===========================================================================
def test_22_retry_and_idempotency_rules() -> None:
    """A `database_write` step with any retry mode other than `never`, an
    `idempotency_key_required` step without an idempotency key source,
    and a `safe`-retry API step whose operation is not idempotent must
    each be rejected as `invalid_retry_policy` or
    `missing_idempotency_key_source` respectively."""
    with new_workspace() as paths:

        def unsafe_write_retry(raw: dict[str, Any]) -> None:
            find_step(raw, "r01-s02-init")["retry_mode"] = "safe"

        mutate_runbook(paths, "r01-bootstrap-session", unsafe_write_retry)
        # r01-bootstrap-session is already recorded as applied (and thus
        # already matched/non-executable) on every fixture deployment.
        # Clear that record so it is treated as not-yet-applied and its
        # steps are planned and validated (rather than short-circuiting
        # either as "matched" or as a checksum-drift rejection, both of
        # which are covered by other tests).
        clear_applied_runbooks(paths, "deployment-staging-v2")
        write_requests(
            paths,
            [
                base_request(
                    "req-bad-write-retry",
                    "deployment-staging-v2",
                    ["r01-bootstrap-session"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-bad-write-retry", "invalid_retry_policy")
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-bad-write-retry"
        )
        assert row["runbook_id_or_null"] == "r01-bootstrap-session"
        assert row["step_id_or_null"] == "r01-s02-init"

    with new_workspace() as paths:

        def missing_key(raw: dict[str, Any]) -> None:
            find_step(raw, "r06-s02-unlock")["idempotency_key_source_or_null"] = None

        mutate_runbook(paths, "r06-unlock-route", missing_key)
        write_requests(
            paths,
            [
                base_request(
                    "req-missing-key", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_rejection(
            paths, "req-missing-key", "missing_idempotency_key_source"
        )
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-missing-key"
        )
        assert row["runbook_id_or_null"] == "r06-unlock-route"
        assert row["step_id_or_null"] == "r06-s02-unlock"

    with new_workspace() as paths:

        def safe_on_non_idempotent(raw: dict[str, Any]) -> None:
            step = find_step(raw, "r02-s02-auth")
            step["retry_mode"] = "safe"

        mutate_runbook(paths, "r02-authenticate-vault", safe_on_non_idempotent)
        write_requests(
            paths,
            [
                base_request(
                    "req-unsafe-retry",
                    "deployment-staging-v2",
                    ["r02-authenticate-vault"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-unsafe-retry", "invalid_retry_policy")
        row = next(
            r for r in actual["rejection_rows"] if r["request_id"] == "req-unsafe-retry"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"

    # Multi-failure: invalid_retry_policy outranks missing_idempotency_key_source.
    with new_workspace() as paths:

        def bad_r02(raw: dict[str, Any]) -> None:
            find_step(raw, "r02-s02-auth")["retry_mode"] = "safe"

        def bad_r06(raw: dict[str, Any]) -> None:
            find_step(raw, "r06-s02-unlock")["idempotency_key_source_or_null"] = None

        mutate_runbook(paths, "r02-authenticate-vault", bad_r02)
        mutate_runbook(paths, "r06-unlock-route", bad_r06)
        write_requests(
            paths,
            [
                base_request(
                    "req-retry-over-key",
                    "deployment-staging-v2",
                    ["r06-unlock-route"],
                )
            ],
        )
        actual = expect_rejection(paths, "req-retry-over-key", "invalid_retry_policy")
        row = next(
            r
            for r in actual["rejection_rows"]
            if r["request_id"] == "req-retry-over-key"
        )
        assert row["runbook_id_or_null"] == "r02-authenticate-vault"
        assert row["step_id_or_null"] == "r02-s02-auth"


# ===========================================================================
# 23. Deterministic runbook and step ordering
# ===========================================================================
def test_23_deterministic_runbook_and_step_ordering() -> None:
    """Executable runbooks receive contiguous 1-based topological positions
    by UTF-8 runbook_id order among executable members (not schedule order).
    Within each runbook, steps execute by step_rank / requires_step_ids."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-ordering", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-ordering")
        selected = [
            r
            for r in rows_for(actual, "selected_runbook_rows", "req-ordering")
            if r["executable"]
        ]
        by_utf8 = sorted(selected, key=lambda r: r["runbook_id"].encode("utf-8"))
        positions = [r["topological_position_or_null"] for r in by_utf8]
        assert positions == list(range(1, len(positions) + 1))
        # Row order among executable follows topological_position ascending.
        row_order = [
            r
            for r in rows_for(actual, "selected_runbook_rows", "req-ordering")
            if r["executable"]
        ]
        assert [r["topological_position_or_null"] for r in row_order] == list(
            range(1, len(row_order) + 1)
        )

        steps = sorted(
            rows_for(actual, "step_rows", "req-ordering"),
            key=lambda s: s["global_step_position"],
        )
        assert [s["global_step_position"] for s in steps] == list(
            range(1, len(steps) + 1)
        )
        r06_steps = [
            s["step_id"] for s in steps if s["runbook_id"] == "r06-unlock-route"
        ]
        assert r06_steps == ["r06-s01-prep", "r06-s02-unlock", "r06-s03-done"]


# ===========================================================================
# 24. Database and local batching
# ===========================================================================
def test_24_database_and_local_batching() -> None:
    """No batch may contain more steps than `maximum_steps_per_batch`, and
    lowering that limit must deterministically produce more, smaller
    batches whose concatenated step ids still equal the full, correctly
    ordered step sequence."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-batch-default", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-batch-default")
        default_profile = tomllib.loads(
            paths["release_config"].read_text(encoding="utf-8")
        )
        limit = default_profile["maximum_steps_per_batch"]
        for batch in rows_for(actual, "batch_rows", "req-batch-default"):
            assert len(batch["step_ids"]) <= limit

    with new_workspace() as paths:
        mutate_release_profile(
            paths, lambda raw: raw.__setitem__("maximum_steps_per_batch", 1)
        )
        write_requests(
            paths,
            [
                base_request(
                    "req-batch-tight", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-batch-tight")
        batches = sorted(
            rows_for(actual, "batch_rows", "req-batch-tight"),
            key=lambda b: b["batch_index"],
        )
        assert batches[0]["batch_index"] == 0
        assert [b["batch_index"] for b in batches] == list(range(len(batches)))
        for batch in batches:
            assert len(batch["step_ids"]) <= 1
        steps = sorted(
            rows_for(actual, "step_rows", "req-batch-tight"),
            key=lambda s: s["global_step_position"],
        )
        assert [sid for b in batches for sid in b["step_ids"]] == [
            s["step_id"] for s in steps
        ]


# ===========================================================================
# 25. API isolation and dependency boundaries
# ===========================================================================
def test_25_api_isolation_and_dependency_boundaries() -> None:
    """Every `api_request` step must be the sole member of its batch, and
    batch boundaries elsewhere must be driven only by execution mode and
    capability availability."""
    with new_workspace() as paths:
        write_requests(
            paths,
            [
                base_request(
                    "req-api-isolation", "deployment-staging-v2", ["r06-unlock-route"]
                )
            ],
        )
        actual = expect_accepted(paths, "req-api-isolation")
        batches = rows_for(actual, "batch_rows", "req-api-isolation")
        for batch in batches:
            if batch["execution_mode"] == "api_request":
                assert len(batch["step_ids"]) == 1, (
                    "an api_request batch must contain exactly one step"
                )
        step_kind_by_id = {
            s["step_id"]: s["step_kind"]
            for s in rows_for(actual, "step_rows", "req-api-isolation")
        }
        for batch in batches:
            if batch["execution_mode"] == "api_request":
                (sid,) = batch["step_ids"]
                assert step_kind_by_id[sid] == "api_request"


# ===========================================================================
# 26. Coupled accepted release (full multi-request integration)
# ===========================================================================
def test_26_coupled_accepted_release() -> None:
    """Running the full, unmutated four-request fixture batch end to end
    must produce the expected per-request statuses and focused replacement,
    capability-subtraction, and rejection-shape properties without comparing
    the entire report outside ``test_28``."""
    with new_workspace() as paths:
        result = run_candidate(paths)
        assert_success(result, paths)
        actual = load_candidate_report(paths)
        for request_id, expected_status in (
            ("request-accepted-v2", "accepted"),
            ("request-api-v1-mismatch", "rejected"),
            ("request-audit-capability-missing", "rejected"),
            ("request-checksum-drift", "rejected"),
        ):
            row = next(
                r for r in actual["request_rows"] if r["request_id"] == request_id
            )
            assert row["status"] == expected_status

        selected = {
            r["runbook_id"]: r
            for r in rows_for(actual, "selected_runbook_rows", "request-accepted-v2")
        }
        assert "r08-safe-clue-sync" in selected
        assert "r07-legacy-clue-sync" not in selected
        edges = rows_for(actual, "dependency_edge_rows", "request-accepted-v2")
        assert any(e["edge_type"] == "replacement_provides" for e in edges)
        assert_caps_absent_from_execution_rows(
            actual, "request-accepted-v2", ["state:vault_session_ready"]
        )

        accepted_batches = rows_for(actual, "batch_rows", "request-accepted-v2")
        assert len(accepted_batches) > 0
        for rejected_id in (
            "request-api-v1-mismatch",
            "request-audit-capability-missing",
            "request-checksum-drift",
        ):
            assert rows_for(actual, "selected_runbook_rows", rejected_id) == []


# ===========================================================================
# 27. Mutation locality and five-seed invariance
# ===========================================================================
def test_27_mutation_locality_and_five_seed_invariance() -> None:
    """Granting a single missing capability to one deployment must change
    the report only for the request(s) against that deployment, flipping
    exactly that request from rejected to accepted while leaving every
    other request's rows byte-identical; and re-ordering the physically
    unordered array fields inside the runbook fixtures (and the physical
    line order of the request batch) under five different seeds must
    never change the candidate's output at all."""
    with new_workspace() as paths:
        baseline_result = run_candidate(paths)
        assert_success(baseline_result, paths)
        baseline = load_candidate_report(paths)

        add_capability(paths, "deployment-audit-v3", "db:table:audit_events")
        result = run_candidate(paths)
        assert_success(result, paths)
        mutated_actual = load_candidate_report(paths)

        affected = "request-audit-capability-missing"
        for key in (
            "request_rows",
            "selected_runbook_rows",
            "dependency_edge_rows",
            "step_rows",
            "batch_rows",
            "rejection_rows",
        ):
            base_other = [r for r in baseline[key] if r.get("request_id") != affected]
            mut_other = [
                r for r in mutated_actual[key] if r.get("request_id") != affected
            ]
            assert base_other == mut_other, (
                f"unrelated rows in {key} changed after a local capability grant"
            )

        base_row = next(
            r for r in baseline["request_rows"] if r["request_id"] == affected
        )
        mut_row = next(
            r for r in mutated_actual["request_rows"] if r["request_id"] == affected
        )
        assert base_row["status"] == "rejected"
        assert mut_row["status"] == "accepted"

    with new_workspace() as baseline_paths:
        baseline_result = run_candidate(baseline_paths)
        assert_success(baseline_result, baseline_paths)
        baseline_text = baseline_paths["output"].read_text(encoding="utf-8")

    for seed in (7, 19, 41, 83, 127):
        with new_workspace() as paths:
            _shuffle_fixture_tree(paths, random.Random(seed))
            result = run_candidate(paths)
            assert_success(result, paths)
            shuffled_text = paths["output"].read_text(encoding="utf-8")
            assert shuffled_text == baseline_text, (
                f"seed {seed} changed candidate output"
            )


def _shuffle_fixture_tree(paths: dict[str, Path], rng: random.Random) -> None:
    """Reorder every unordered array field across the fixture tree without
    changing its semantic content, recomputing checksums as needed."""
    for path in sorted(paths["runbooks"].glob("*.yaml")):
        raw = load_yaml(path)

        def shuf(values: list[Any]) -> list[Any]:
            out = list(values)
            rng.shuffle(out)
            return out

        for field in (
            "requires",
            "conflicts",
            "replaces",
            "provides_runbook_ids",
            "allowed_api_revisions",
            "allowed_database_revisions",
        ):
            raw[field] = shuf(raw[field])
        for step in raw["steps"]:
            for field in (
                "requires_step_ids",
                "required_capabilities",
                "provided_capabilities",
                "accepted_statuses",
            ):
                step[field] = shuf(step[field])
        raw["steps"] = shuf(raw["steps"])
        raw["checksum_sha256"] = compute_runbook_checksum_from_raw(raw)
        dump_yaml(path, raw)

    contract = load_contract(paths)
    ops = list(contract["operations"])
    rng.shuffle(ops)
    for op in ops:
        op["accepted_request_content_types"] = list(
            op["accepted_request_content_types"]
        )
        rng.shuffle(op["accepted_request_content_types"])
        op["success_statuses"] = list(op["success_statuses"])
        rng.shuffle(op["success_statuses"])
        op["required_capabilities"] = list(op["required_capabilities"])
        rng.shuffle(op["required_capabilities"])
    contract["operations"] = ops
    dump_contract(paths, contract)

    lines = paths["requests"].read_text(encoding="utf-8").splitlines()
    rng.shuffle(lines)
    paths["requests"].write_text("\n".join(lines) + "\n", encoding="utf-8")


# ===========================================================================
# 28. Strict, complete report and deterministic fatal behavior
# ===========================================================================
def test_28_strict_complete_report_and_deterministic_fatal_behavior() -> None:
    """Strict complete-report gate with separated diagnostics:

    1. Private golden integrity (sidecar SHA-256 validates the golden only).
    2. Candidate semantic equality against the parsed golden (not a candidate hash).
    3. Candidate serialization (pretty 2-space JSON, one trailing LF).
    4. Candidate determinism across two unchanged runs.
    5. Deterministic fatal cleanup behavior.
    """
    # --- Private golden integrity (fixture only; not a candidate hash) ---
    _golden_bytes, expected = load_golden_report()

    with new_workspace() as paths:
        result = run_candidate(paths)
        assert_success(result, paths)
        raw_text = paths["output"].read_text(encoding="utf-8")

        # --- Candidate serialization (candidate-relative) ---
        assert raw_text.endswith("\n") and not raw_text.endswith("\n\n"), (
            "output must end with exactly one trailing newline"
        )
        assert " \n" not in raw_text and not raw_text.rstrip("\n").endswith(" "), (
            "output must not contain trailing whitespace on lines"
        )
        actual = json.loads(raw_text)
        assert set(actual) == REQUEST_FIELDS, (
            f"unexpected top-level keys: {set(actual) - REQUEST_FIELDS}"
        )
        reparsed = candidate_pretty_json(actual)
        assert raw_text == reparsed, (
            "output is not canonically pretty-printed 2-space JSON with a trailing LF"
        )

        # --- Candidate semantic equality (parsed JSON; never golden hash) ---
        mismatches = diff_json(expected, actual, limit=8)
        assert not mismatches, (
            "semantic report mismatch (showing up to 8 paths):\n"
            + "\n".join(mismatches)
        )

    # --- Candidate determinism (byte-identical across unchanged runs) ---
    with new_workspace() as paths:
        first_result = run_candidate(paths)
        assert_success(first_result, paths)
        first_text = paths["output"].read_text(encoding="utf-8")
        paths["output"].unlink()
        second_result = run_candidate(paths)
        assert_success(second_result, paths)
        second_text = paths["output"].read_text(encoding="utf-8")
        assert first_text == second_text, (
            "identical inputs must produce byte-identical output"
        )

    # --- Fatal behavior (independent of the complete golden report) ---
    with new_workspace() as paths:
        paths["output"].write_text('{"stale": true}\n', encoding="utf-8")
        tmp_sibling = paths["output"].with_suffix(paths["output"].suffix + ".tmp")
        tmp_sibling.write_text("partial", encoding="utf-8")
        paths["api_contract"].write_text("not json at all", encoding="utf-8")
        first = run_candidate(paths)
        assert_fatal(paths, first)
        assert first.returncode != 0
        assert (first.stderr or "").strip() != ""
        assert not paths["output"].exists(), "stale final output must be removed"
        assert not tmp_sibling.exists(), "temporary sibling output must be removed"
        second = run_candidate(paths)
        assert_fatal(paths, second)
        assert first.returncode == second.returncode, (
            "fatal exit code must be deterministic"
        )
        assert (first.stderr or "").strip() == (second.stderr or "").strip(), (
            "fatal stderr must be deterministic across repeated runs"
        )

    # Temporary deterministic-rejection bundle (not part of permanent fixtures):
    # unknown targets, missing transitive deps, and dual unsatisfied replacements.
    with new_workspace() as paths:
        write_synthetic_runbook(
            paths,
            "syn-beta",
            requires=["missing-alpha"],
        )
        write_synthetic_runbook(
            paths,
            "syn-alpha",
            requires=["missing-zeta"],
        )
        write_synthetic_runbook(paths, "old-z")
        write_synthetic_runbook(paths, "old-a")
        write_synthetic_runbook(
            paths,
            "dep-anchor",
            requires=["old-z", "old-a"],
        )

        def set_prefs(raw: dict[str, Any]) -> None:
            raw["replacement_preferences"] = {
                "old-z": "new-z-missing",
                "old-a": "new-a-missing",
            }

        mutate_release_profile(paths, set_prefs)
        write_requests(
            paths,
            [
                base_request(
                    "req-det-unknown",
                    "deployment-staging-v2",
                    ["missing-zeta", "missing-alpha"],
                ),
                base_request(
                    "req-det-missing",
                    "deployment-staging-v2",
                    ["syn-beta", "syn-alpha"],
                ),
                base_request(
                    "req-det-repl",
                    "deployment-staging-v2",
                    ["dep-anchor"],
                ),
            ],
        )
        reports: list[bytes] = []
        for _ in range(8):
            if paths["output"].exists():
                paths["output"].unlink()
            for sibling in list(paths["output"].parent.iterdir()):
                if sibling.name != paths["output"].name and (
                    sibling.name.startswith(paths["output"].name)
                    or sibling.suffix == ".tmp"
                ):
                    sibling.unlink()
            payload = run_candidate_bytes(paths)
            reports.append(payload)
            leftovers = [
                p for p in paths["output"].parent.iterdir() if p != paths["output"]
            ]
            assert leftovers == [], f"unexpected temporary output siblings: {leftovers}"
            actual = json.loads(payload.decode("utf-8"))
            by_id = {r["request_id"]: r for r in actual["rejection_rows"]}
            assert by_id["req-det-unknown"]["reason"] == "unknown_target_runbook"
            assert by_id["req-det-unknown"]["runbook_id_or_null"] == "missing-alpha"
            assert by_id["req-det-missing"]["reason"] == "missing_dependency"
            assert by_id["req-det-missing"]["runbook_id_or_null"] == "missing-zeta"
            assert by_id["req-det-repl"]["reason"] == "replacement_unsatisfied"
            assert by_id["req-det-repl"]["runbook_id_or_null"] == "old-a"
            assert by_id["req-det-repl"]["details"]["related_ids"] == [
                "old-a",
                "new-a-missing",
            ]
        assert len({r for r in reports}) == 1, (
            "deterministic-rejection bundle must be byte-identical across processes"
        )
