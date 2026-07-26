"""Validate covariance-coupled minimum-cycle policy safety."""

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
    "hidden-e",
)
INPUT_FILES = (
    "cases.csv",
    "states.csv",
    "cluster_roster.csv",
    "priors.csv",
    "regularizers.csv",
    "records.csv",
)
HEADER = (
    "case_id",
    "selected_candidate",
    "selected_policy",
    "feasible_count",
    "policy_score",
    "robust_policy_return",
    "minimum_cycle_mean",
    "critical_cycle",
    "critical_cycle_length",
    "cycle_covariance_penalty",
    "effective_sample_size",
    "support_edge_count",
    "minimum_edge_support",
    "cv_loss",
    "deletion_code",
    "deletion_change_count",
    "worst_deletion_safety",
    "worst_deletion_scenario_code",
    "maximum_deletion_covariance",
    "stability_checksum",
    "audit_signature",
)
FLOAT_FIELDS = (
    "policy_score",
    "robust_policy_return",
    "minimum_cycle_mean",
    "cycle_covariance_penalty",
    "effective_sample_size",
    "minimum_edge_support",
    "cv_loss",
    "worst_deletion_safety",
    "maximum_deletion_covariance",
)
INT_FIELDS = (
    "feasible_count",
    "critical_cycle_length",
    "support_edge_count",
    "deletion_change_count",
    "worst_deletion_scenario_code",
    "stability_checksum",
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


def write_csv(
    path: Path,
    header: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=header,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


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
    timeout: int = 600,
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
        assert value == pytest.approx(
            target,
            abs=ABS_TOLERANCE,
            rel=0,
        )
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


def copy_surface(surface: str, name: str) -> Path:
    destination = GENERATED_ROOT / name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(surface_root(surface), destination)
    return destination


def rewrite_relations(
    destination: Path,
    transform,
) -> None:
    for name in INPUT_FILES:
        header, rows = read_csv(destination / name)
        transformed_header, transformed_rows = transform(name, header, rows)
        write_csv(
            destination / name,
            transformed_header,
            transformed_rows,
        )


def build_row_header_permutation() -> Path:
    destination = copy_surface("hidden-b", "row-header-permutation")

    def transform(name, header, rows):
        del name
        return tuple(reversed(header)), list(reversed(rows))

    rewrite_relations(destination, transform)
    return destination


def build_ratio_affine_surface() -> Path:
    destination = copy_surface("hidden-a", "ratio-affine")

    def transform(name, header, rows):
        if name == "records.csv":
            for index, row in enumerate(rows):
                scale = (0.0625, 0.25, 0.5, 1.0)[index % 4]
                row["target_prob"] = format(
                    float(row["target_prob"]) * scale,
                    ".17g",
                )
                row["behavior_prob"] = format(
                    float(row["behavior_prob"]) * scale,
                    ".17g",
                )
                row["reward"] = format(
                    float(row["reward"]) + 700.0,
                    ".17g",
                )
                row["cost"] = format(
                    float(row["cost"]) + 700.0,
                    ".17g",
                )
                row["noise_a"] = str(-50000 - index)
                row["source_id"] = f"changed::{index:08d}"
        return header, rows

    rewrite_relations(destination, transform)
    return destination


def build_cluster_translation_surface() -> Path:
    destination = copy_surface("hidden-e", "cluster-translation")

    def transform(name, header, rows):
        if name in {"cluster_roster.csv", "records.csv"}:
            for row in rows:
                row["cluster"] = str(int(row["cluster"]) + 1000)
        return header, rows

    rewrite_relations(destination, transform)
    return destination


def build_exposure_scaled_surface() -> Path:
    destination = copy_surface("hidden-d", "exposure-scale")

    def transform(name, header, rows):
        if name == "cluster_roster.csv":
            case_ids = sorted({row["case_id"] for row in rows})
            factors = {
                case_id: (0.125, 2.0, 16.0)[index % 3]
                for index, case_id in enumerate(case_ids)
            }
            for row in rows:
                row["exposure_weight"] = format(
                    float(row["exposure_weight"])
                    * factors[row["case_id"]],
                    ".17g",
                )
        return header, rows

    rewrite_relations(destination, transform)
    return destination


def fnv1a(payload: str) -> str:
    value = 2_166_136_261
    for byte in payload.encode():
        value ^= byte
        value = (value * 16_777_619) & 0xFFFFFFFF
    return f"{value:08x}"


def decision_code(value: str) -> int:
    return math.floor(10_000_000 * float(value) + 0.5)


def signature_payload(row: dict[str, str]) -> str:
    parts = (
        row["case_id"],
        row["selected_candidate"],
        row["selected_policy"],
        row["critical_cycle"],
        row["deletion_code"],
        str(decision_code(row["policy_score"])),
        str(decision_code(row["robust_policy_return"])),
        str(decision_code(row["minimum_cycle_mean"])),
        str(decision_code(row["cycle_covariance_penalty"])),
        str(decision_code(row["effective_sample_size"])),
        str(int(row["support_edge_count"])),
        str(decision_code(row["minimum_edge_support"])),
        str(decision_code(row["cv_loss"])),
        str(int(row["deletion_change_count"])),
        str(int(row["worst_deletion_scenario_code"])),
        str(int(row["stability_checksum"])),
    )
    return "|".join(parts)


def build_case_translation_surface() -> tuple[Path, tuple[dict[str, str], ...]]:
    destination = copy_surface("hidden-c", "case-translation")
    mapping = {
        row["case_id"]: f"translated::{row['case_id']}"
        for row in EXPECTED["hidden-c"]
    }

    def transform(name, header, rows):
        del name
        for row in rows:
            row["case_id"] = mapping[row["case_id"]]
        return header, rows

    rewrite_relations(destination, transform)
    expected = []
    for original in EXPECTED["hidden-c"]:
        row = dict(original)
        row["case_id"] = mapping[row["case_id"]]
        row["audit_signature"] = fnv1a(signature_payload(row))
        expected.append(row)
    return destination, tuple(expected)


def build_malformed(profile: str) -> Path:
    destination = copy_surface("public", f"malformed-{profile}")
    if profile == "missing-relation":
        (destination / "cluster_roster.csv").unlink()
        return destination
    relations = {
        name: read_csv(destination / name) for name in INPUT_FILES
    }
    target_case = min(
        row["case_id"] for row in relations["cases.csv"][1]
    )
    if profile == "duplicate-roster":
        header, rows = relations["cluster_roster.csv"]
        target = next(row for row in rows if row["case_id"] == target_case)
        rows.append(dict(target))
        write_csv(destination / "cluster_roster.csv", header, rows)
    elif profile == "incomplete-prior":
        header, rows = relations["priors.csv"]
        removed = False
        retained = []
        for row in rows:
            if row["case_id"] == target_case and not removed:
                removed = True
            else:
                retained.append(row)
        write_csv(destination / "priors.csv", header, retained)
    elif profile == "nonpositive-prior":
        header, rows = relations["priors.csv"]
        target = next(row for row in rows if row["case_id"] == target_case)
        target["prior_mass"] = "0"
        write_csv(destination / "priors.csv", header, rows)
    elif profile == "duplicate-candidate-rank":
        header, rows = relations["regularizers.csv"]
        same_case = [
            row for row in rows if row["case_id"] == target_case
        ]
        same_case[1]["candidate_rank"] = same_case[0]["candidate_rank"]
        write_csv(destination / "regularizers.csv", header, rows)
    elif profile == "unknown-cluster":
        header, rows = relations["records.csv"]
        target = next(row for row in rows if row["case_id"] == target_case)
        target["cluster"] = "999999"
        write_csv(destination / "records.csv", header, rows)
    elif profile == "zero-behavior":
        header, rows = relations["records.csv"]
        target = next(row for row in rows if row["case_id"] == target_case)
        target["behavior_prob"] = "0"
        write_csv(destination / "records.csv", header, rows)
    elif profile == "incomplete-grid":
        header, rows = relations["records.csv"]
        first = next(row for row in rows if row["case_id"] == target_case)
        rows = [
            row
            for row in rows
            if not (
                row["case_id"] == first["case_id"]
                and row["policy_id"] == first["policy_id"]
                and row["cluster"] == first["cluster"]
            )
        ]
        write_csv(destination / "records.csv", header, rows)
    else:
        raise AssertionError(f"unknown malformed profile {profile}")
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
    """Match every protected case field to its golden result."""
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
    """Require the exact unquoted schema and one row per case."""
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
    """Preserve all semantics when every relation is reversed."""
    permuted = run_candidate(
        build_row_header_permutation(),
        "row-header-permutation",
    )
    assert permuted.header == HEADER
    assert_semantic_rows(permuted.rows, EXPECTED["hidden-b"])


def test_ratio_and_reward_cost_affine_invariance():
    """Preserve results after ratio-preserving and utility-preserving edits."""
    transformed = run_candidate(
        build_ratio_affine_surface(),
        "ratio-affine",
    )
    assert_semantic_rows(transformed.rows, EXPECTED["hidden-a"])


def test_cluster_identifier_translation_invariance():
    """Preserve rank-based certificates under monotone cluster relabeling."""
    transformed = run_candidate(
        build_cluster_translation_surface(),
        "cluster-translation",
    )
    assert_semantic_rows(transformed.rows, EXPECTED["hidden-e"])


def test_exposure_scale_invariance():
    """Preserve outputs when all exposures in a case share one scale."""
    transformed = run_candidate(
        build_exposure_scaled_surface(),
        "exposure-scale",
    )
    assert_semantic_rows(transformed.rows, EXPECTED["hidden-d"])


def test_case_identifier_translation_updates_only_provenance():
    """Translate case IDs while retaining metrics and recomputing signatures."""
    data_root, expected = build_case_translation_surface()
    transformed = run_candidate(data_root, "case-translation")
    assert_semantic_rows(transformed.rows, expected)


def test_default_invocation_is_byte_deterministic():
    """Honor defaults and reproduce the public output byte for byte."""
    explicit = run_candidate(surface_root("public"), "public")
    output_root = Path("/app/outputs")
    output_root.chmod(0o777)
    output = output_root / "results.csv"
    output.unlink(missing_ok=True)
    completed = sandbox_command(output_root, ["/app/run.sh"])
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes() == explicit.raw


@pytest.mark.parametrize(
    "profile",
    (
        "missing-relation",
        "duplicate-roster",
        "incomplete-prior",
        "nonpositive-prior",
        "duplicate-candidate-rank",
        "unknown-cluster",
        "zero-behavior",
        "incomplete-grid",
    ),
)
def test_malformed_bundle_is_rejected(profile: str):
    """Reject malformed relational bundles without emitting a result."""
    data_root = build_malformed(profile)
    run_root = CANDIDATE_ROOT / f"failure-{profile}"
    make_writable(run_root)
    copied_data = run_root / "data"
    shutil.copytree(data_root, copied_data)
    output = run_root / "results.csv"
    completed = sandbox_command(
        run_root,
        ["/app/run.sh", str(copied_data), str(output)],
        timeout=120,
    )
    assert completed.returncode != 0
    assert not output.exists()


def test_candidate_cannot_read_protected_verifier_paths():
    """Deny access to goldens, verifier code, solution, and reward."""
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


def test_protected_surfaces_are_load_bearing():
    """Ensure the fixtures exercise tuning, fallback, cycles, and refits."""
    rows = [row for surface in SURFACES for row in EXPECTED[surface]]
    assert len(rows) == 60
    assert len({row["selected_candidate"] for row in rows}) >= 6
    assert len({row["selected_policy"] for row in rows}) >= 7
    assert {
        int(row["critical_cycle_length"]) for row in rows
    } >= {1, 2, 3, 4, 5}
    assert sum(int(row["feasible_count"]) == 0 for row in rows) >= 20
    assert sum(int(row["deletion_change_count"]) for row in rows) >= 240
    assert len({row["audit_signature"] for row in rows}) == len(rows)
    pair_rows = EXPECTED["hidden-e"]
    assert sum(row["deletion_code"].count("|") >= 30 for row in pair_rows) >= 4
