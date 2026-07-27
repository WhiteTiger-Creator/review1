"""Vaccine cold-chain cross-artifact verification."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ENV = APP / "environment"
BIN = APP / "bin" / "vcs_sim"
INVENTORY = APP / "output" / "inventory.json"
SHIPMENTS = APP / "output" / "shipments.csv"
COMPLIANCE = APP / "output" / "compliance.log"
ANALYTICS = APP / "output" / "analytics.json"
CHECKPOINT = ENV / "state" / "checkpoint.json"
POLICY = ENV / "config" / "coldchain_policy.toml"


def rebuild_runner() -> None:
    proc = subprocess.run(
        ["bash", "-c", "cd /app/environment && go build -o /app/bin/vcs_sim ./e5"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"go build failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


@pytest.fixture(scope="module", autouse=True)
def ensure_driver() -> None:
    rebuild_runner()
    assert BIN.exists(), f"missing driver: {BIN}"


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, capture_output=True, check=False, cwd="/app")
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(command)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def reset_artifacts() -> None:
    for path in (INVENTORY, SHIPMENTS, COMPLIANCE, ANALYTICS):
        if path.exists():
            path.unlink()
    if CHECKPOINT.exists():
        CHECKPOINT.unlink()


def run_scenario(scenario: str, rounds: int | None = None) -> None:
    cmd = [str(BIN), "run", "--scenario", scenario]
    if rounds is not None:
        cmd.extend(["--rounds", str(rounds)])
    run_checked(cmd)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows() -> list[dict[str, str]]:
    with SHIPMENTS.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_compliance() -> list[str]:
    if not COMPLIANCE.exists():
        return []
    return [ln.strip() for ln in COMPLIANCE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def sum_facility_field(inventory: dict, field: str) -> int:
    total = 0
    for fac in inventory.get("facilities", {}).values():
        total += int(fac.get(field, 0))
    return total


def delivered_from_csv(rows: list[dict[str, str]]) -> int:
    total = 0
    for row in rows:
        if row["status"] in {"delivered", "recovered"} and row["temp_ok"] == "true":
            total += int(row["doses"])
    return total


def violation_count(lines: list[str]) -> int:
    return sum(1 for ln in lines if "STATUS=violation" in ln)


def expected_state_digest(inventory: dict) -> str:
    """Recompute digest per operator_guide.md (independent of exporter code)."""
    facilities = inventory.get("facilities", {})
    parts: list[str] = []
    for fid in sorted(facilities.keys()):
        batches = facilities[fid].get("batches", []) or []
        chunk: list[str] = []
        for batch in sorted(batches, key=lambda b: str(b.get("batch_id", ""))):
            chunk.append(
                f"{fid}|{batch.get('batch_id')}|{int(batch.get('doses', 0))}|"
                f"{batch.get('status')}"
            )
        parts.append(";".join(chunk))
    raw = "||".join(parts)
    proc = subprocess.run(
        ["sha256sum"],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"sha256sum failed: {proc.stderr}")
    return proc.stdout.split()[0][:16]


def assert_cross_artifact(scenario: str) -> None:
    inventory = load_json(INVENTORY)
    analytics = load_json(ANALYTICS)
    rows = read_csv_rows()
    lines = parse_compliance()

    assert inventory["schema_version"] == 1, scenario
    assert inventory["scenario_id"] == scenario, scenario
    digest = expected_state_digest(inventory)
    assert inventory["state_digest"] == digest, scenario
    assert analytics["state_digest"] == digest, scenario
    assert analytics["total_usable_doses"] == sum_facility_field(inventory, "usable_doses"), scenario
    assert analytics["total_quarantined_doses"] == sum_facility_field(
        inventory, "quarantined_doses"
    ), scenario
    assert analytics["total_delivered"] == delivered_from_csv(rows), scenario

    temp_summary = inventory["temperature_summary"]
    assert temp_summary["violations"] == violation_count(lines), scenario
    assert analytics["compliance_pass"] is True, scenario

    lineage_rows = inventory.get("lineage")
    assert isinstance(lineage_rows, list), scenario
    for row in lineage_rows:
        parent = row.get("parent_id", "")
        if not parent:
            continue
        child = row["batch_id"]
        gen = int(row["split_gen"])
        assert gen > 0, f"lineage split_gen for {child} in {scenario}"
        assert child == f"{parent}-s{gen}", f"lineage id mismatch for {child} in {scenario}"


class TestVaccineColdChain:
    def test_policy_toml_contains_correct_values(self) -> None:
        """coldchain_policy.toml must carry the operator_guide contract values."""
        content = POLICY.read_text(encoding="utf-8")
        assert 'parent_link_mode = "enforce_parent"' in content
        assert 'child_id_mode = "increment_generation"' in content
        assert 'temp_on_recovery = "preserve_transit"' in content
        assert 'quarantine_mode = "honor_violation"' in content
        assert 'in_transit_release = "release"' in content

    def test_alpha_baseline_consistency(self) -> None:
        """Clean two-round flow keeps inventory, CSV, log, and analytics aligned."""
        reset_artifacts()
        run_scenario("alpha")
        assert_cross_artifact("alpha")
        assert CHECKPOINT.exists()

    def test_beta_temp_excursion_quarantine(self) -> None:
        """Excursion above 8C quarantines affected doses across exports."""
        reset_artifacts()
        run_scenario("beta")
        inventory = load_json(INVENTORY)
        analytics = load_json(ANALYTICS)
        assert analytics["total_quarantined_doses"] > 0
        rows = read_csv_rows()
        assert any(r["temp_ok"] == "false" for r in rows)
        assert inventory["temperature_summary"]["violations"] >= 1
        assert_cross_artifact("beta")

    def test_gamma_split_lineage(self) -> None:
        """Partial transfer records parent-linked child batch lineage."""
        reset_artifacts()
        run_scenario("gamma")
        inventory = load_json(INVENTORY)
        child_rows = [r for r in inventory["lineage"] if r.get("parent_id") == "B200"]
        assert child_rows, "expected child lineage for B200"
        assert any(r["batch_id"] == "B200-s1" for r in child_rows)
        assert_cross_artifact("gamma")

    def test_delta_recovery_reconciliation(self) -> None:
        """Interrupted shipment recovery respects temperature history and totals."""
        reset_artifacts()
        run_scenario("delta")
        rows = read_csv_rows()
        recovered = next(r for r in rows if r["shipment_id"] == "S030")
        assert recovered["status"] == "recovered"
        assert recovered["temp_ok"] == "false"
        inventory = load_json(INVENTORY)
        assert sum_facility_field(inventory, "quarantined_doses") >= int(recovered["doses"])
        # Origin must release the in-transit hold so doses are not double-counted.
        origin_batches = inventory["facilities"]["MFG-A"]["batches"]
        b100 = next(b for b in origin_batches if b["batch_id"] == "B100")
        assert int(b100["doses"]) == 600
        assert_cross_artifact("delta")

    def test_epsilon_incremental_production(self) -> None:
        """Round-2 production arrival appears in inventory without static writes."""
        reset_artifacts()
        run_scenario("epsilon")
        inventory = load_json(INVENTORY)
        found = False
        for fac in inventory["facilities"].values():
            for batch in fac.get("batches", []):
                if batch.get("batch_id") == "B300":
                    found = True
        assert found
        assert_cross_artifact("epsilon")

    def test_zeta_expiry_exclusion(self) -> None:
        """Expired batches are excluded from usable totals."""
        reset_artifacts()
        run_scenario("zeta")
        inventory = load_json(INVENTORY)
        expired = False
        for fac in inventory["facilities"].values():
            for batch in fac.get("batches", []):
                if batch.get("batch_id") == "B900" and batch.get("status") == "expired":
                    expired = True
        assert expired
        assert_cross_artifact("zeta")

    def test_mutation_demand_changes_outcome(self) -> None:
        """Mutating scenario shipment doses changes derived analytics totals."""
        reset_artifacts()
        run_scenario("alpha")
        baseline = load_json(ANALYTICS)["total_delivered"]
        scenario_path = ENV / "scenarios" / "alpha.json"
        original = scenario_path.read_text(encoding="utf-8")
        try:
            data = json.loads(original)
            data["shipments"][0]["doses"] = 50
            scenario_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            reset_artifacts()
            run_scenario("alpha")
            mutated = load_json(ANALYTICS)["total_delivered"]
            assert mutated != baseline
            assert mutated < baseline
        finally:
            scenario_path.write_text(original, encoding="utf-8")

    def test_mutation_threshold_changes_quarantine(self) -> None:
        """Raising scenario temp reading increases quarantine totals."""
        reset_artifacts()
        scenario_path = ENV / "scenarios" / "beta.json"
        original = scenario_path.read_text(encoding="utf-8")
        try:
            data = json.loads(original)
            data["shipments"][0]["temp_c"] = 12.0
            scenario_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            run_scenario("beta")
            analytics = load_json(ANALYTICS)
            assert analytics["total_quarantined_doses"] >= 250
            assert_cross_artifact("beta")
        finally:
            scenario_path.write_text(original, encoding="utf-8")

    def test_mutation_policy_temp_recovery(self) -> None:
        """Flipping temp_on_recovery must change recovered shipment temp_ok."""
        reset_artifacts()
        original = POLICY.read_text(encoding="utf-8")
        try:
            if 'temp_on_recovery = "preserve_transit"' in original:
                first_expect = "false"
                flipped = original.replace(
                    'temp_on_recovery = "preserve_transit"',
                    'temp_on_recovery = "reset_ok"',
                )
                second_expect = "true"
            else:
                first_expect = "true"
                flipped = original.replace(
                    'temp_on_recovery = "reset_ok"',
                    'temp_on_recovery = "preserve_transit"',
                )
                second_expect = "false"

            rebuild_runner()
            run_scenario("delta")
            rows = read_csv_rows()
            recovered = next(r for r in rows if r["shipment_id"] == "S030")
            assert recovered["temp_ok"] == first_expect

            POLICY.write_text(flipped, encoding="utf-8")
            rebuild_runner()
            reset_artifacts()
            run_scenario("delta")
            rows = read_csv_rows()
            recovered = next(r for r in rows if r["shipment_id"] == "S030")
            assert recovered["temp_ok"] == second_expect
        finally:
            POLICY.write_text(original, encoding="utf-8")
            rebuild_runner()

    def test_no_verdict_sentinels(self) -> None:
        """Exports must not contain hardcoded verdict sentinel tokens."""
        reset_artifacts()
        run_scenario("alpha")
        blob = (
            INVENTORY.read_text(encoding="utf-8")
            + ANALYTICS.read_text(encoding="utf-8")
            + COMPLIANCE.read_text(encoding="utf-8")
        )
        for token in ("_ok", "_green", "_valid", "_passes", "stays_green"):
            assert token not in blob

    def test_checkpoint_advances(self) -> None:
        """Checkpoint round advances after multi-round simulation."""
        reset_artifacts()
        run_scenario("alpha", rounds=2)
        cp = load_json(CHECKPOINT)
        assert int(cp["round"]) == 2

    def test_checkpoint_cross_run_resume(self) -> None:
        """Second runner invocation must resume batches from checkpoint state."""
        reset_artifacts()
        run_scenario("alpha", rounds=1)
        cp1 = load_json(CHECKPOINT)
        assert int(cp1["round"]) == 1
        run_scenario("alpha", rounds=2)
        cp2 = load_json(CHECKPOINT)
        assert int(cp2["round"]) == 2
        assert_cross_artifact("alpha")
        # Batches must still be addressable after JSON round-trip.
        inventory = load_json(INVENTORY)
        total_batches = sum(len(f.get("batches", [])) for f in inventory["facilities"].values())
        assert total_batches >= 2

    def test_compliance_log_format(self) -> None:
        """Compliance log lines follow SEQ/ROUND/EVENT structure."""
        reset_artifacts()
        run_scenario("beta")
        pattern = re.compile(r"^SEQ=\d+ ROUND=\d+ EVENT=\w+")
        for line in parse_compliance():
            assert pattern.match(line), line
