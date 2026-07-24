"""Behavioral verifier for the ABI transition release manifests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

import pytest


TASK_ROOT = Path(os.environ.get("TASK_FILE_DIR", "/app/task_file"))
TEST_ROOT = Path(__file__).resolve().parent
SCAN_ROOT = TASK_ROOT / "scan_input"
OUTPUT_ROOT = TASK_ROOT / "output"
CASES = (
    ("abi_case.txt", "abi_plan.json"),
    ("branching_case.txt", "branching_plan.json"),
    ("cohort_case.txt", "cohort_plan.json"),
    ("tie_case.txt", "tie_plan.json"),
)
INPUT_HASHES = {
    "abi_case.txt": "873276fee204b6ad937d2aae94e8a2f33c3f36443ac484e5a28db51c1d363a24",
    "branching_case.txt": "6ab3233a6232963bcd61ebca0312481f632e697db629bf03a66b0debf9c76635",
    "cohort_case.txt": "d1537c475c9fa402f870c4b534edf68a981dc0a7d77622d73c465c227a60a197",
    "tie_case.txt": "6e2225a0362feb00e6dc4779e3fb01074d16fc60c57455868a5b8e03b9886532",
}


def sha256_file(path: Path) -> str:
    """Return a stable digest for an agent-visible inventory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def invoke(binary: Path, input_path: Path, output_path: Path) -> dict:
    """Run the isolated reference optimizer for one release inventory."""
    subprocess.run(
        [str(binary), str(input_path), str(output_path)],
        check=True,
        timeout=180,
        cwd=TASK_ROOT,
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def expected_plans() -> dict[str, dict]:
    """Compute canonical manifests independently from the submitted JSON files."""
    build = Path(tempfile.mkdtemp(prefix=f".abi-reference-{secrets.token_hex(12)}-", dir="/tmp"))
    reference = build / f".{secrets.token_hex(24)}"
    plans: dict[str, dict] = {}
    try:
        subprocess.run(
            ["g++", "-std=c++20", "-O2", str(TEST_ROOT / "reference.cpp"), "-o", str(reference)],
            check=True,
            timeout=60,
        )
        for input_name, _ in CASES:
            output_path = build / f".{secrets.token_hex(24)}"
            plans[input_name] = invoke(reference, SCAN_ROOT / input_name, output_path)
        return plans
    finally:
        shutil.rmtree(build, ignore_errors=True)


def assert_shape(data: object, wave_count: int) -> None:
    """Check the exact manifest fields, types, lengths, and identifier ordering."""
    assert isinstance(data, dict)
    assert set(data) == {
        "migration_cost",
        "peak_bridge_mb",
        "peak_rollback_mb",
        "total_action_minutes",
        "waves",
    }
    for field in ("migration_cost", "peak_bridge_mb", "peak_rollback_mb", "total_action_minutes"):
        assert type(data[field]) is int
    assert isinstance(data["waves"], list)
    assert len(data["waves"]) == wave_count
    for index, wave in enumerate(data["waves"], start=1):
        assert isinstance(wave, dict)
        assert set(wave) == {
            "wave_index",
            "action_ids",
            "build_minutes",
            "test_minutes",
            "active_bridge_package_ids",
            "remaining_old_package_ids",
            "awaiting_validation_package_ids",
            "validated_package_ids",
        }
        assert wave["wave_index"] == index
        assert type(wave["build_minutes"]) is int
        assert type(wave["test_minutes"]) is int
        for field in (
            "action_ids",
            "active_bridge_package_ids",
            "remaining_old_package_ids",
            "awaiting_validation_package_ids",
            "validated_package_ids",
        ):
            assert isinstance(wave[field], list)
            assert all(isinstance(item, str) for item in wave[field])
            assert wave[field] == sorted(wave[field])


def wave_count(path: Path) -> int:
    """Read the declared number of release waves from an inventory."""
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields[:2] == ["PARAM", "wave_count"]:
            return int(fields[2])
    raise AssertionError(f"wave_count missing from {path}")


def test_agent_visible_inputs_are_unchanged() -> None:
    """The four dependency inventories must remain byte-for-byte unchanged."""
    for input_name, _ in CASES:
        path = SCAN_ROOT / input_name
        assert path.is_file(), f"missing {input_name}"
        assert sha256_file(path) == INPUT_HASHES[input_name]


def test_submitted_plans_have_exact_schema() -> None:
    """Every requested release manifest must exist and follow the documented JSON schema."""
    for input_name, output_name in CASES:
        output_path = OUTPUT_ROOT / output_name
        assert output_path.is_file(), f"missing /app/task_file/output/{output_name}"
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert_shape(data, wave_count(SCAN_ROOT / input_name))


def test_submitted_plans_are_exactly_optimal(expected_plans: dict[str, dict]) -> None:
    """Each manifest must equal the independently recomputed canonical optimum for its graph."""
    for input_name, output_name in CASES:
        actual = json.loads((OUTPUT_ROOT / output_name).read_text(encoding="utf-8"))
        assert actual == expected_plans[input_name]
