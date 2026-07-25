"""Validate robust minimum-cycle policy safety on protected surfaces."""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

SURFACES = (
    "public",
    "hidden-a",
    "hidden-b",
    "hidden-c",
    "hidden-d",
    "ratio-scaled",
)
INPUT_FILES = (
    "cases.csv",
    "states.csv",
    "priors.csv",
    "regularizers.csv",
    "records.csv",
)
HEADER = (
    "case_id",
    "selected_lambda",
    "selected_policy",
    "feasible_count",
    "policy_score",
    "robust_policy_return",
    "minimum_cycle_mean",
    "critical_cycle",
    "effective_sample_size",
    "cv_loss",
    "deletion_code",
    "deletion_change_count",
    "worst_deletion_safety",
    "worst_deletion_scenario_code",
    "stability_checksum",
    "audit_signature",
)
FLOAT_FIELDS = (
    "policy_score",
    "robust_policy_return",
    "minimum_cycle_mean",
    "effective_sample_size",
    "cv_loss",
    "worst_deletion_safety",
    "stability_checksum",
)
INT_FIELDS = (
    "feasible_count",
    "deletion_change_count",
    "worst_deletion_scenario_code",
)
ABS_TOLERANCE = 3e-8
CANDIDATE_UID = 65534
CANDIDATE_GID = 65534
CANDIDATE_ROOT = Path("/dev/shm/bank-cycle-candidate-runs")
GENERATED_ROOT = Path("/tmp/bank-cycle-verifier-surfaces")
LANDLOCK = Path("/tests/landlock_exec.py")


@dataclass(frozen=True)
class CandidateResult:
    header: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    raw: bytes


def surface_root(surface: str) -> Path:
    if surface == "public":
        return Path("/app/data")
    return Path("/tests/fixtures") / surface


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        return tuple(reader.fieldnames or ()), list(reader)


def expected_rows(surface: str) -> tuple[dict[str, str], ...]:
    header, rows = read_csv(Path("/tests/golden") / f"{surface}.csv")
    assert header == HEADER
    return tuple(rows)


EXPECTED = {surface: expected_rows(surface) for surface in SURFACES}
CASE_PARAMETERS = tuple(
    (surface, row["case_id"])
    for surface in SURFACES
    for row in EXPECTED[surface]
)
RUN_CACHE: dict[str, CandidateResult] = {}


def make_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, CANDIDATE_UID, CANDIDATE_GID)
    path.chmod(0o700)


def sandbox_command(
    write_root: Path,
    command: list[str],
    *,
    timeout: int = 240,
) -> subprocess.CompletedProcess[str]:
    temporary = write_root / "tmp"
    make_writable(temporary)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(write_root),
            "TMPDIR": str(temporary),
            "LC_ALL": "C",
        }
    )
    return subprocess.run(
        [
            "python3",
            str(LANDLOCK),
            "--write",
            str(write_root),
            "--uid",
            str(CANDIDATE_UID),
            "--gid",
            str(CANDIDATE_GID),
            "--",
            *command,
        ],
        cwd="/app",
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def run_candidate(data_root: Path, cache_key: str) -> CandidateResult:
    cached = RUN_CACHE.get(cache_key)
    if cached is not None:
        return cached
    run_root = CANDIDATE_ROOT / cache_key
    if run_root.exists():
        shutil.rmtree(run_root)
    make_writable(run_root)
    copied_data = run_root / "data"
    shutil.copytree(data_root, copied_data)
    output = run_root / "results.csv"
    completed = sandbox_command(
        run_root,
        ["/app/run.sh", str(copied_data), str(output)],
    )
    assert completed.returncode == 0, (
        f"candidate failed on {cache_key}: "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )
    assert output.is_file(), f"candidate did not create output for {cache_key}"
    raw = output.read_bytes()
    header, rows = read_csv(output)
    result = CandidateResult(header, tuple(rows), raw)
    RUN_CACHE[cache_key] = result
    return result


def assert_scalar(actual: str, expected: str, field: str) -> None:
    if field in FLOAT_FIELDS:
        value = float(actual)
        target = float(expected)
        assert math.isfinite(value), f"{field} must be finite"
        assert value == pytest.approx(target, abs=ABS_TOLERANCE, rel=0)
    elif field in INT_FIELDS:
        assert re.fullmatch(r"-?[0-9]+", actual), (
            f"{field} must be a base-10 integer"
        )
        assert int(actual) == int(expected)
    else:
        assert actual == expected


def assert_semantic_rows(
    actual: tuple[dict[str, str], ...],
    expected: tuple[dict[str, str], ...],
) -> None:
    assert len(actual) == len(expected)
    for actual_row, expected_row in zip(actual, expected, strict=True):
        for field in HEADER:
            assert_scalar(actual_row[field], expected_row[field], field)


def build_row_header_permutation() -> Path:
    destination = GENERATED_ROOT / "row-header-permutation"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(surface_root("hidden-b"), destination)
    for name in INPUT_FILES:
        header, rows = read_csv(destination / name)
        reversed_header = tuple(reversed(header))
        with (destination / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=reversed_header,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(reversed(rows))
    return destination


@pytest.fixture(scope="session", autouse=True)
def clean_candidate_area():
    """Reset private writable areas before and after verifier execution."""
    for root in (CANDIDATE_ROOT, GENERATED_ROOT):
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
    yield
    for root in (CANDIDATE_ROOT, GENERATED_ROOT):
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("surface,case_id", CASE_PARAMETERS)
def test_case_semantics(surface: str, case_id: str):
    """Match every protected case field to its independent golden result."""
    result = run_candidate(surface_root(surface), surface)
    actual_by_id = {row["case_id"]: row for row in result.rows}
    expected_by_id = {row["case_id"]: row for row in EXPECTED[surface]}
    assert case_id in actual_by_id
    actual = actual_by_id[case_id]
    expected = expected_by_id[case_id]
    assert set(actual) == set(HEADER)
    for field in HEADER:
        assert_scalar(actual[field], expected[field], field)


@pytest.mark.parametrize("surface", SURFACES)
def test_surface_schema_and_cardinality(surface: str):
    """Require the exact compact schema and one row per expected case."""
    result = run_candidate(surface_root(surface), surface)
    assert result.header == HEADER
    assert len(result.rows) == len(EXPECTED[surface])
    assert b'"' not in result.raw
    assert all(
        re.fullmatch(r"[0-9a-f]{8}", row["audit_signature"])
        for row in result.rows
    )


@pytest.mark.parametrize("surface", SURFACES)
def test_case_order_is_canonical(surface: str):
    """Require unique case rows in canonical identifier order."""
    result = run_candidate(surface_root(surface), surface)
    case_ids = [row["case_id"] for row in result.rows]
    assert case_ids == sorted(case_ids)
    assert len(case_ids) == len(set(case_ids))


def test_row_and_header_order_invariance():
    """Preserve semantic graph results after all relations are reversed."""
    permuted = run_candidate(
        build_row_header_permutation(),
        "row-header-permutation",
    )
    assert permuted.header == HEADER
    assert_semantic_rows(permuted.rows, EXPECTED["hidden-b"])


def test_ratio_and_affine_invariance():
    """Preserve results under ratio scaling and a reward-cost shift."""
    original = run_candidate(surface_root("hidden-a"), "hidden-a")
    transformed = run_candidate(surface_root("ratio-scaled"), "ratio-scaled")
    assert original.header == transformed.header == HEADER
    assert_semantic_rows(transformed.rows, original.rows)


def test_default_invocation_is_byte_deterministic():
    """Honor invocation defaults and reproduce identical output bytes."""
    output_root = Path("/app/outputs")
    output_root.chmod(0o777)
    temporary = output_root / "tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    make_writable(temporary)
    output = output_root / "results.csv"
    snapshots = []
    for _ in range(2):
        output.unlink(missing_ok=True)
        completed = sandbox_command(output_root, ["/app/run.sh"])
        assert completed.returncode == 0, completed.stderr
        snapshots.append(output.read_bytes())
    assert snapshots[0] == snapshots[1]
    header, rows = read_csv(output)
    assert header == HEADER
    assert_semantic_rows(tuple(rows), EXPECTED["public"])


def test_candidate_cannot_read_protected_verifier_paths():
    """Deny candidate access to goldens, verifier code, solution, and reward."""
    write_root = CANDIDATE_ROOT / "sandbox-probe"
    make_writable(write_root)
    completed = sandbox_command(
        write_root,
        [
            "/bin/sh",
            "-c",
            (
                "! /bin/cat /tests/golden/public.csv >/dev/null 2>&1 && "
                "! /bin/cat /tests/test_outputs.py >/dev/null 2>&1 && "
                "! /bin/cat /solution/estimate.R >/dev/null 2>&1 && "
                "! printf x >>/logs/verifier/reward.txt 2>/dev/null"
            ),
        ],
    )
    assert completed.returncode == 0, completed.stderr


def test_golden_surfaces_are_load_bearing():
    """Ensure hidden graphs exercise distinct models, cycles, and refits."""
    rows = [row for surface in SURFACES[:-1] for row in EXPECTED[surface]]
    assert len(rows) == 70
    assert len({row["selected_lambda"] for row in rows}) >= 4
    assert len({row["selected_policy"] for row in rows}) >= 8
    assert len({row["critical_cycle"] for row in rows}) >= 55
    assert sum(int(row["deletion_change_count"]) for row in rows) >= 275
    assert len({row["audit_signature"] for row in rows}) == len(rows)
    assert any(
        int(row["deletion_change_count"]) >= 10
        for row in EXPECTED["hidden-d"]
    )
