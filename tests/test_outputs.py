"""Verifier for the hall certification replay report."""

import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
OUT = APP / "output" / "certification_report.json"
ONE_OUT = APP / "output" / "one_site.json"
SITE_NAMES = ["sr_arden", "sr_bryce", "sr_cinder", "sr_dover", "sr_elgin", "sr_gale", "sr_fenwick", "sr_composite"]
EXPECTED = json.loads((Path(__file__).with_name("rows.json")).read_text())
EXPECTED_ROWS = EXPECTED["sites"]
EXPECTED_PROGRAM = EXPECTED["program_attestation"]
STAT_KEYS = [
    "approval_blocks",
    "capacity_trims",
    "certified_count",
    "compute_blocks",
    "maintenance_blocks",
    "network_blocks",
    "rack_count",
    "readiness_index",
    "region_rejections",
    "storage_blocks",
]


def replay_all():
    subprocess.run(["make", "-C", "/app/environment", "all"], check=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    subprocess.run(
        [
            "/app/environment/bin/certctl",
            "--all",
            "--out",
            "/app/output/certification_report.json",
        ],
        check=True,
    )


@pytest.fixture(scope="session", autouse=True)
def rebuild_and_replay():
    """Rebuild the controller and regenerate the certification report."""
    replay_all()


def load_report():
    assert OUT.is_file(), "certification_report.json missing"
    return json.loads(OUT.read_text())


def row_by_name(report, name):
    for row in report.get("sites", []):
        if row.get("name") == name:
            return row
    return None


def test_schema_version():
    """The published document declares schema_version 1."""
    assert load_report().get("schema_version") == 1


def test_every_hall_listed():
    """Every hall in the published index appears exactly once."""
    names = [r.get("name") for r in load_report().get("sites", [])]
    assert sorted(names) == sorted(SITE_NAMES)


@pytest.mark.parametrize("spec", EXPECTED_ROWS, ids=lambda s: s["name"])
def test_hall_row_counters(spec):
    """Each hall row reports the counters the certification contract requires."""
    row = row_by_name(load_report(), spec["name"])
    assert row is not None, f"missing row for {spec['name']}"
    actual = {k: row.get(k) for k in STAT_KEYS}
    assert actual == {k: spec[k] for k in STAT_KEYS}


@pytest.mark.parametrize("spec", EXPECTED_ROWS, ids=lambda s: s["name"])
def test_hall_row_attestation(spec):
    """Each hall row seals the attestation over its own published counters."""
    row = row_by_name(load_report(), spec["name"])
    assert row is not None, f"missing row for {spec['name']}"
    mark = row.get("attestation", "")
    assert isinstance(mark, str) and len(mark) == 64 and mark == mark.lower()
    assert mark == spec["attestation"]


def test_counters_account_for_every_rack():
    """Certified racks plus stage removals account for the full hall inventory."""
    for row in load_report().get("sites", []):
        removed = (
            row["compute_blocks"]
            + row["storage_blocks"]
            + row["network_blocks"]
            + row["approval_blocks"]
            + row["maintenance_blocks"]
            + row["region_rejections"]
            + row["capacity_trims"]
        )
        assert row["certified_count"] + removed == row["rack_count"], row["name"]


def test_program_attestation():
    """The programme attestation seals the sorted per-hall attestations."""
    report = load_report()
    mark = report.get("program_attestation", "")
    assert isinstance(mark, str) and len(mark) == 64 and mark == mark.lower()
    assert mark == EXPECTED_PROGRAM


def test_replay_is_reproducible():
    """Deleting the document and replaying reproduces identical sealed values."""
    before = {r["name"]: r["attestation"] for r in load_report()["sites"]}
    OUT.unlink()
    subprocess.run(
        [
            "/app/environment/bin/certctl",
            "--all",
            "--out",
            "/app/output/certification_report.json",
        ],
        check=True,
    )
    after = load_report()
    for row in after["sites"]:
        assert row["attestation"] == before[row["name"]], row["name"]


@pytest.mark.parametrize("spec", [EXPECTED_ROWS[0], EXPECTED_ROWS[-1]], ids=lambda s: s["name"])
def test_single_hall_matches_full_replay(spec):
    """A single-hall replay produces the same row as the full replay."""
    if ONE_OUT.exists():
        ONE_OUT.unlink()
    subprocess.run(
        [
            "/app/environment/bin/certctl",
            "--site",
            spec["name"],
            "--out",
            "/app/output/one_site.json",
        ],
        check=True,
    )
    data = json.loads(ONE_OUT.read_text())
    row = data["sites"][0]
    assert {k: row.get(k) for k in STAT_KEYS} == {k: spec[k] for k in STAT_KEYS}
    assert row["attestation"] == spec["attestation"]
