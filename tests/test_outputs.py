from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from helpers.wakeclock_reference import reconcile

APP_DIR = Path(os.environ.get("APP_DIR", "/app"))
TESTS_DIR = Path(__file__).resolve().parent
PUBLIC_FIXTURE_ROOT = TESTS_DIR / "fixtures" / "public_case"
CANONICAL_OCCURRENCE_ID = re.compile(
    r"^[^|]+\|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\|-?\d+\|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)


def iter_fixture_occurrence_ids(fixture_root: Path) -> list[str]:
    occurrence_ids: list[str] = []
    snapshot = json.loads((fixture_root / "state" / "snapshot.json").read_text())
    for item in snapshot.get("pending", []):
        occurrence_ids.append(str(item["occurrence_id"]))
    for cursor in snapshot.get("cursors", {}).values():
        if cursor:
            occurrence_ids.append(str(cursor))
    journal_path = fixture_root / "state" / "journal.jsonl"
    if journal_path.exists():
        for line in journal_path.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                occurrence_ids.extend(str(value) for value in record.get("occurrence_ids", []))
    spool_dir = fixture_root / "state" / "spool"
    if spool_dir.is_dir():
        for path in spool_dir.glob("*.json"):
            record = json.loads(path.read_text())
            occurrence_ids.extend(str(value) for value in record.get("occurrence_ids", []))
    return occurrence_ids


def assert_fixture_occurrence_ids_are_canonical(fixture_root: Path) -> None:
    for occurrence_id in iter_fixture_occurrence_ids(fixture_root):
        assert occurrence_id.count("|") == 3, occurrence_id
        assert CANONICAL_OCCURRENCE_ID.match(occurrence_id), occurrence_id


@pytest.fixture(scope="session", autouse=True)
def _validate_public_fixture_occurrence_ids() -> None:
    assert_fixture_occurrence_ids_are_canonical(PUBLIC_FIXTURE_ROOT)


@pytest.fixture(scope="session")
def binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    destination = tmp_path_factory.mktemp("bin") / "wakeclock"
    subprocess.run(
        ["go", "build", "-o", str(destination), "./cmd/wakeclock"],
        cwd=APP_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return destination


def copy_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    units = tmp_path / "units"
    state = tmp_path / "state"
    clock = tmp_path / "clock.jsonl"
    shutil.copytree(PUBLIC_FIXTURE_ROOT / "units", units)
    shutil.copytree(PUBLIC_FIXTURE_ROOT / "state", state)
    (state / "spool").mkdir(exist_ok=True)
    shutil.copy2(PUBLIC_FIXTURE_ROOT / "clock" / "trace.jsonl", clock)
    return units, state, clock


def run_candidate(
    binary: Path,
    units: Path,
    state: Path,
    clock: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(binary),
            "reconcile",
            "--units",
            str(units),
            "--state",
            str(state),
            "--clock",
            str(clock),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def assert_matches_reference(
    binary: Path,
    units: Path,
    state: Path,
    clock: Path,
    output: Path,
) -> dict[str, object]:
    expected_report, expected_state, expected_journal, expected_spools = reconcile(
        units, state, clock
    )
    result = run_candidate(binary, units, state, clock, output)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert json.loads(output.read_text()) == expected_report
    assert json.loads((state / "snapshot.json").read_text()) == expected_state
    actual_journal = [
        json.loads(line)
        for line in (state / "journal.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert actual_journal == expected_journal
    for activation_id, spool in expected_spools.items():
        assert json.loads((state / "spool" / f"{activation_id}.json").read_text()) == spool
    assert output.read_bytes().endswith(b"\n")
    return expected_report


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def write_trace(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(item, separators=(",", ":")) + "\n" for item in events))


def initial_state(utc: str) -> dict[str, object]:
    return {
        "schema_version": "wakeclock.state.v1",
        "trace_seq": 0,
        "clock_utc": utc,
        "high_water_utc": utc,
        "boot_id": "initial",
        "pending": [],
        "committed_ids": [],
        "last_activation": {},
        "cursors": {},
    }


def unit(
    unit_id: str,
    timezone: str,
    hour: int,
    minute: int,
    *,
    delay: int = 0,
    accuracy: int = 0,
    depends_on: list[str] | None = None,
    priority: int = 0,
    persistent: bool = True,
    cap: int = 8,
) -> dict[str, object]:
    return {
        "schema_version": "wakeclock.unit.v1",
        "unit_id": unit_id,
        "timezone": timezone,
        "hour": hour,
        "minute": minute,
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "persistent": persistent,
        "random_delay_sec": delay,
        "accuracy_sec": accuracy,
        "depends_on": depends_on or [],
        "priority": priority,
        "enabled": True,
        "catch_up_cap": cap,
        "salt": f"{unit_id}-salt",
    }


def test_public_fold_recovery_contract_matches_independent_model(
    binary: Path, tmp_path: Path
) -> None:
    """The bundled fold, dependency, and recovery stream matches an independent model."""
    units, state, clock = copy_case(tmp_path)
    report = assert_matches_reference(binary, units, state, clock, tmp_path / "out/report.json")
    fold_ids = [
        occurrence_id
        for activation in report["activations"]
        for occurrence_id in activation["occurrence_ids"]
        if occurrence_id.startswith("index|2026-11-01T01:30:00|")
    ]
    assert len(fold_ids) == 2
    assert len(set(fold_ids)) == 2
    paired = [
        activation
        for activation in report["activations"]
        if set(activation["unit_ids"]) == {"index", "archive"}
    ]
    assert all(activation["unit_ids"] == ["index", "archive"] for activation in paired)


def test_spring_gap_and_fall_fold_are_utc_first(binary: Path, tmp_path: Path) -> None:
    """UTC-first enumeration must omit a spring gap and preserve both fall-fold instants."""
    units = tmp_path / "units"
    units.mkdir()
    write_json(units / "fold.timer.json", unit("fold", "America/New_York", 1, 30))
    write_json(units / "gap.timer.json", unit("gap", "America/New_York", 2, 30))
    state = tmp_path / "state"
    (state / "spool").mkdir(parents=True)
    write_json(state / "snapshot.json", initial_state("2026-03-08T05:00:00Z"))
    (state / "journal.jsonl").write_text("")
    clock = tmp_path / "clock.jsonl"
    write_trace(
        clock,
        [
            {"seq": 1, "kind": "advance", "utc": "2026-03-08T08:00:00Z"},
            {"seq": 2, "kind": "advance", "utc": "2026-11-01T07:00:00Z"},
        ],
    )
    report = assert_matches_reference(binary, units, state, clock, tmp_path / "report.json")
    all_ids = [
        occurrence_id
        for activation in report["activations"]
        for occurrence_id in activation["occurrence_ids"]
    ]
    assert not any(item.startswith("gap|2026-03-08T02:30:00|") for item in all_ids)
    assert sum(item.startswith("fold|2026-11-01T01:30:00|") for item in all_ids) == 2


def test_delay_and_results_ignore_unit_filename_order(binary: Path, tmp_path: Path) -> None:
    """Stable delay and relevant activations must ignore filenames and unrelated units."""
    units_a, state_a, clock_a = copy_case(tmp_path / "a")
    units_b, state_b, clock_b = copy_case(tmp_path / "b")
    for index, path in enumerate(sorted(units_b.glob("*.timer.json"), reverse=True)):
        path.rename(units_b / f"renamed-{index}.timer.json")
    write_json(
        units_b / "unrelated.timer.json",
        unit("unrelated", "UTC", 23, 59, delay=999, accuracy=1),
    )
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    report_a = assert_matches_reference(binary, units_a, state_a, clock_a, out_a)
    report_b = assert_matches_reference(binary, units_b, state_b, clock_b, out_b)
    relevant_a = [item for item in report_a["activations"] if "unrelated" not in item["unit_ids"]]
    relevant_b = [item for item in report_b["activations"] if "unrelated" not in item["unit_ids"]]
    assert relevant_a == relevant_b


def test_coalescing_uses_delayed_windows_and_dependency_topology(
    binary: Path, tmp_path: Path
) -> None:
    """Delayed-window intersection and dependency topology determine one dispatch order."""
    units = tmp_path / "units"
    units.mkdir()
    write_json(units / "base.timer.json", unit("base", "UTC", 0, 1, accuracy=30, priority=1))
    write_json(
        units / "child.timer.json",
        unit("child", "UTC", 0, 2, accuracy=30, depends_on=["base"], priority=99),
    )
    state = tmp_path / "state"
    (state / "spool").mkdir(parents=True)
    snapshot = initial_state("2026-01-01T00:04:00Z")
    snapshot["pending"] = [
        {
            "unit_id": "base",
            "occurrence_id": "base|2026-01-01T00:01:00|0|2026-01-01T00:01:00Z",
            "scheduled_local": "2026-01-01T00:01:00",
            "scheduled_utc": "2026-01-01T00:01:00Z",
            "offset_sec": 0,
            "delayed_utc": "2026-01-01T00:02:10Z",
            "accuracy_sec": 30,
            "priority": 1,
            "depends_on": [],
        },
        {
            "unit_id": "child",
            "occurrence_id": "child|2026-01-01T00:02:00|0|2026-01-01T00:02:00Z",
            "scheduled_local": "2026-01-01T00:02:00",
            "scheduled_utc": "2026-01-01T00:02:00Z",
            "offset_sec": 0,
            "delayed_utc": "2026-01-01T00:02:20Z",
            "accuracy_sec": 30,
            "priority": 99,
            "depends_on": ["base"],
        },
    ]
    write_json(state / "snapshot.json", snapshot)
    (state / "journal.jsonl").write_text("")
    clock = tmp_path / "clock.jsonl"
    write_trace(clock, [{"seq": 1, "kind": "set", "utc": "2026-01-01T00:04:00Z"}])
    report = assert_matches_reference(binary, units, state, clock, tmp_path / "report.json")
    assert report["activations"][0]["unit_ids"] == ["base", "child"]


def test_prepare_only_is_discarded_and_retried(binary: Path, tmp_path: Path) -> None:
    """A lone prepare is removed while its occurrence remains available for one retry."""
    units = tmp_path / "units"
    units.mkdir()
    write_json(units / "job.timer.json", unit("job", "UTC", 0, 0))
    state = tmp_path / "state"
    (state / "spool").mkdir(parents=True)
    pending = {
        "unit_id": "job",
        "occurrence_id": "job|2026-01-01T00:00:00|0|2026-01-01T00:00:00Z",
        "scheduled_local": "2026-01-01T00:00:00",
        "scheduled_utc": "2026-01-01T00:00:00Z",
        "offset_sec": 0,
        "delayed_utc": "2026-01-01T00:00:00Z",
        "accuracy_sec": 0,
        "priority": 0,
        "depends_on": [],
    }
    snapshot = initial_state("2026-01-01T00:00:00Z")
    snapshot["pending"] = [pending]
    write_json(state / "snapshot.json", snapshot)
    prepare = {
        "activation_id": "orphan-prepare",
        "phase": "prepare",
        "group_id": "orphan-group",
        "occurrence_ids": [pending["occurrence_id"]],
    }
    (state / "journal.jsonl").write_text(json.dumps(prepare, separators=(",", ":")) + "\n")
    clock = tmp_path / "clock.jsonl"
    write_trace(clock, [{"seq": 1, "kind": "advance", "utc": "2026-01-01T00:00:01Z"}])
    report = assert_matches_reference(binary, units, state, clock, tmp_path / "report.json")
    assert report["recovered"] == [
        {"activation_id": "orphan-prepare", "decision": "discarded_prepare"}
    ]
    assert len(report["activations"]) == 1


@pytest.mark.parametrize("phase_count", [2, 3])
def test_spooled_and_committed_partial_state_recovers_once(
    binary: Path, tmp_path: Path, phase_count: int
) -> None:
    """Spooled and committed partial dispatches recover exactly once from durable evidence."""
    units = tmp_path / "units"
    units.mkdir()
    write_json(units / "job.timer.json", unit("job", "UTC", 0, 0))
    state = tmp_path / "state"
    (state / "spool").mkdir(parents=True)
    pending = {
        "unit_id": "job",
        "occurrence_id": "job|2026-01-01T00:00:00|0|2026-01-01T00:00:00Z",
        "scheduled_local": "2026-01-01T00:00:00",
        "scheduled_utc": "2026-01-01T00:00:00Z",
        "offset_sec": 0,
        "delayed_utc": "2026-01-01T00:00:00Z",
        "accuracy_sec": 0,
        "priority": 0,
        "depends_on": [],
    }
    snapshot = initial_state("2026-01-01T00:00:00Z")
    snapshot["pending"] = [pending]
    write_json(state / "snapshot.json", snapshot)
    activation_id = "partial-activation"
    group_id = "partial-group"
    records = [
        {
            "activation_id": activation_id,
            "phase": phase,
            "group_id": group_id,
            "occurrence_ids": [pending["occurrence_id"]],
        }
        for phase in ("prepare", "spool", "commit")[:phase_count]
    ]
    (state / "journal.jsonl").write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records)
    )
    write_json(
        state / "spool" / f"{activation_id}.json",
        {
            "activation_id": activation_id,
            "group_id": group_id,
            "effective_utc": "2026-01-01T00:00:00Z",
            "unit_ids": ["job"],
            "occurrence_ids": [pending["occurrence_id"]],
        },
    )
    clock = tmp_path / "clock.jsonl"
    clock.write_text("")
    report = assert_matches_reference(binary, units, state, clock, tmp_path / "report.json")
    expected = "completed_spool" if phase_count == 2 else "replayed_commit"
    assert report["recovered"] == [{"activation_id": activation_id, "decision": expected}]
    first_state = (state / "snapshot.json").read_bytes()
    first_journal = (state / "journal.jsonl").read_bytes()
    second = run_candidate(binary, units, state, clock, tmp_path / "second.json")
    assert second.returncode == 0
    assert (state / "snapshot.json").read_bytes() == first_state
    assert (state / "journal.jsonl").read_bytes() == first_journal
    assert json.loads((tmp_path / "second.json").read_text())["recovered"] == []


def test_backward_clock_rerun_is_idempotent(binary: Path, tmp_path: Path) -> None:
    """Backward clock history and a completed rerun must not recreate durable work."""
    units, state, clock = copy_case(tmp_path)
    output = tmp_path / "first.json"
    assert_matches_reference(binary, units, state, clock, output)
    snapshot = (state / "snapshot.json").read_bytes()
    journal = (state / "journal.jsonl").read_bytes()
    spool_bytes = {path.name: path.read_bytes() for path in (state / "spool").glob("*.json")}
    second = run_candidate(binary, units, state, clock, tmp_path / "second.json")
    assert second.returncode == 0
    assert (state / "snapshot.json").read_bytes() == snapshot
    assert (state / "journal.jsonl").read_bytes() == journal
    assert {path.name: path.read_bytes() for path in (state / "spool").glob("*.json")} == spool_bytes
    second_report = json.loads((tmp_path / "second.json").read_text())
    assert second_report["activations"] == []
    assert second_report["recovered"] == []


@pytest.mark.parametrize("invalid_kind", ["cycle", "trace"])
def test_invalid_inputs_preserve_state_and_output(
    binary: Path, tmp_path: Path, invalid_kind: str
) -> None:
    """Invalid dependencies and traces must preserve every durable byte and report sentinel."""
    units, state, clock = copy_case(tmp_path)
    if invalid_kind == "cycle":
        index_path = units / "10-index.timer.json"
        index = json.loads(index_path.read_text())
        index["depends_on"] = ["archive"]
        write_json(index_path, index)
    else:
        write_trace(
            clock,
            [
                {"seq": 2, "kind": "advance", "utc": "2026-11-01T05:00:00Z"},
                {"seq": 1, "kind": "advance", "utc": "2026-11-01T06:00:00Z"},
            ],
        )
    before = {path.relative_to(state): path.read_bytes() for path in state.rglob("*") if path.is_file()}
    output = tmp_path / "report.json"
    output.write_bytes(b"sentinel\n")
    result = run_candidate(binary, units, state, clock, output)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.startswith("wakeclock: ")
    assert result.stderr.count("\n") == 1
    after = {path.relative_to(state): path.read_bytes() for path in state.rglob("*") if path.is_file()}
    assert after == before
    assert output.read_bytes() == b"sentinel\n"
