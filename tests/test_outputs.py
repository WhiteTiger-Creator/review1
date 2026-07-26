"""Verification for orbital salvage fleet command simulator."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPORT_PATH = Path("/app/build/fleet_sortie_ledger.json")
REPORT_FIRST = Path("/logs/verifier/report_first.json")
VERIFIER_DIR = Path("/logs/verifier")
DECK_DIR = Path("/app/sortie_deck")
ROSTER_PATH = DECK_DIR / "roster.json"
APP_DIR = Path("/app")

IMMUTABLE_SHA256: dict[str, str] = {
    "Makefile": "21f5aea858ddab0aaa1f0c1f7aca201a08dc910e67eb0d88c63f6491bab6d868",
    "go.mod": "38d999500507aca6fa98c602855c7bb8723ef06f1c5822e130e6b0f859319695",
    "mission_brief/osf_sortie_contract.json": "720ca12131b2e0e535690d3f738ed28a427825eadcf8ee0ec2002ecc89762873",
    "sortie_deck/roster.json": "8dd9fcc6bf3a2edb72a8ad608c3515044c31946f3d844734dc9f8eebdb8afc6e",
    "sortie_deck/sortie_01.json": "39cfbc14bcc946220b0084355e72e9664861c07a97cd6d8438ef984a7b5808c4",
    "sortie_deck/sortie_02.json": "77fff22077160c2d4f3a619b9ff23bf5a326f9de7a07150045cb3ce44456f15c",
    "sortie_deck/sortie_03.json": "955ba33dd32d8c229aa6fa91bb9b21da415c348fc26c9c6a61c4bb6a76c085c0",
    "sortie_deck/sortie_04.json": "d6367569eadc63f60b497171794cd1c4109c843380cdab0e239b7a59387b4144",
    "sortie_deck/sortie_05.json": "2dd6217fa774675452a1527fdc6142c98db3d8020a61935108ce5b435e706df1",
    "sortie_deck/sortie_06.json": "3442a5de054e5fbaa3977f3a1ade3d3db75a1251016f1a9a2cb5368e4b956ea4",
    "sortie_deck/sortie_07.json": "6320525ad3f33ba81d24fb5d9f3adab1bbc47df1a4d51116b68eea707715a913",
    "sortie_deck/sortie_08.json": "c9c17940f38e2debb9bf9ce44f1edc9f3623808289d4608b4e65e2b9e6cfd1fb",
    "sortie_deck/sortie_09.json": "c71d7092bc65e883daceafced004050fdd763624a3cbfbd2dd71c78a734c4122",
    "sortie_deck/sortie_10.json": "2003202629cde6105ec1340a92deed443c757daaecdf24f75e366cccde3e99bb",
    "sortie_deck/sortie_11.json": "42f80632c418a7d5a62ea37201f408866e1d57826c637d219bd18f60b8c878d0",
    "sortie_deck/sortie_12.json": "c8c9339b73892cc1d8900f75703bb2239cd9b32e77543816f29a7e7088a1a7eb",
    "sortie_deck/sortie_13.json": "aead0b40f959040608dbd2f0fe7229cbd4b39c053ccbf41639d24297cd85e46f",
    "sortie_deck/sortie_14.json": "575e0763a28255fa0a0020962f7927477b444bb2f3ed803726db20a2bced59f4",
    "sortie_deck/sortie_15.json": "afcbe3ff626253e987409297d7bf82e609f390e3e459f7ef6141c8625b6be765",
    "sortie_deck/sortie_16.json": "8946a8bd7433e60a2666c746710db57f57039c22bf9007886293c07d140ad85f",
    "sortie_deck/sortie_17.json": "8a1ce48c8d290e62a3e4767d970af03a729a4ea1e14212b2649d775ad940aab0",
    "sortie_deck/sortie_18.json": "99fe211d426f60adcfd03e6d40bb3057919d8520d9976d64c1eb55e5065919cc",
    "sortie_deck/sortie_19.json": "7c9b3e5b87e8d3b5a88b041c4164acea089dc557ed6ba05e9aaffca6db659ea8",
    "sortie_deck/sortie_20.json": "5fe55f9c88c9e2eccade44b4cab8b0cbcc7b05edb83b533182bda779604ef53a",
}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _perturb_sortie_01() -> None:
    path = DECK_DIR / "sortie_01.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    shutil.copy(path, VERIFIER_DIR / "sortie_01_clean.json")
    obj["fuel_budget"] = 1
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _perturb_sortie_04() -> None:
    path = DECK_DIR / "sortie_04.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    shutil.copy(path, VERIFIER_DIR / "sortie_04_clean.json")
    if obj.get("windows"):
        obj["windows"][0]["close_tick"] = 0
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _run_make(target: str, log_name: str) -> None:
    proc = subprocess.run(
        ["make", target],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)
    (VERIFIER_DIR / log_name).write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        pytest.fail(f"make {target} failed; see /logs/verifier/{log_name}")


def _assert_byte_identical_rerun(prefix: str) -> None:
    REPORT_PATH.unlink(missing_ok=True)
    _run_make("run", f"{prefix}_restore.log")
    shutil.copy(REPORT_PATH, REPORT_FIRST)
    _run_make("run", f"{prefix}_restore2.log")
    if REPORT_PATH.read_bytes() != REPORT_FIRST.read_bytes():
        pytest.fail(f"{prefix} rerun not byte-identical")


def _sortie_row(report: dict[str, Any], sortie_id: str) -> dict[str, Any]:
    for row in report["sorties"]:
        if row["sortie_id"] == sortie_id:
            return row
    raise KeyError(sortie_id)


def _assert_incident(
    sortie_id: str, code: str, entity_id: str | None = None
) -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    row = _sortie_row(report, sortie_id)
    finding = next((i for i in row["incidents"] if i["code"] == code), None)
    assert finding is not None, f"missing {code} in {sortie_id}"
    if entity_id is not None:
        assert finding["entity_id"] == entity_id


@pytest.fixture(scope="session", autouse=True)
def _verifier_grading_setup() -> None:
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("sortie_01_clean.json", "sortie_04_clean.json", "report_first.json"):
        (VERIFIER_DIR / name).unlink(missing_ok=True)
    for path in VERIFIER_DIR.glob("*.log"):
        path.unlink()

    _perturb_sortie_01()
    REPORT_PATH.unlink(missing_ok=True)
    _run_make("build", "build.log")
    _run_make("run", "run_s01.log")
    shutil.copy(REPORT_PATH, REPORT_FIRST)
    _run_make("run", "run_s01_2.log")
    if REPORT_PATH.read_bytes() != REPORT_FIRST.read_bytes():
        pytest.fail("sortie_01 perturbed rerun not byte-identical")

    shutil.copy(VERIFIER_DIR / "sortie_01_clean.json", DECK_DIR / "sortie_01.json")

    _perturb_sortie_04()
    _assert_byte_identical_rerun("s04")
    _assert_incident("sortie_04", "WINDOW_CLOSED", "OWL")

    shutil.copy(VERIFIER_DIR / "sortie_04_clean.json", DECK_DIR / "sortie_04.json")
    _assert_byte_identical_rerun("clean")


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    assert REPORT_PATH.is_file(), f"missing {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_ledger_contract_immutability(report: dict[str, Any]) -> None:
    """Roster order immutability compact JSON and deterministic ledger bytes."""
    expected_ids = [f"sortie_{i:02d}" for i in range(1, 21)]
    roster = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    assert roster["sorties"] == expected_ids
    assert [row["sortie_id"] for row in report["sorties"]] == expected_ids
    for rel, digest in IMMUTABLE_SHA256.items():
        assert _sha256_file(APP_DIR / rel) == digest, f"modified {rel}"
    raw = REPORT_PATH.read_bytes()
    assert raw.endswith(b"\n") and b": " not in raw and b", " not in raw
    canonical = json.dumps(report, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    assert raw == canonical
    assert REPORT_FIRST.is_file() and raw == REPORT_FIRST.read_bytes()


def test_edit_scope_allowlist() -> None:
    """Only allowed top level /app entries may exist."""
    allowed = {"osfcmd", "osflib", "build", "sortie_deck", "mission_brief", "go.mod", "Makefile"}
    for entry in APP_DIR.iterdir():
        assert entry.name in allowed, f"unexpected /app/{entry.name}"


def test_build_artifact_location() -> None:
    """Binary must live under /app/build/salvagectl only."""
    assert not (APP_DIR / "salvagectl").exists()
    assert (APP_DIR / "build" / "salvagectl").is_file()


def test_happy_recovery(report: dict[str, Any]) -> None:
    """Baseline LEO to MEO salvage recovers without incidents."""
    row = _sortie_row(report, "sortie_01")
    assert row["status"] == "RECOVERED"
    assert row["incidents"] == []


def test_fuel_exhausted(report: dict[str, Any]) -> None:
    """Underfueled GEO transfer must emit FUEL_EXHAUSTED."""
    row = _sortie_row(report, "sortie_02")
    assert any(i["code"] == "FUEL_EXHAUSTED" for i in row["incidents"])


def test_hold_overflow(report: dict[str, Any]) -> None:
    """Oversized wreck mass must emit HOLD_OVERFLOW."""
    row = _sortie_row(report, "sortie_03")
    assert any(i["code"] == "HOLD_OVERFLOW" for i in row["incidents"])


def test_window_closed(report: dict[str, Any]) -> None:
    """Burn after window close must emit WINDOW_CLOSED."""
    row = _sortie_row(report, "sortie_04")
    finding = next(i for i in row["incidents"] if i["code"] == "WINDOW_CLOSED")
    assert finding["entity_id"] == "OWL"


def test_debris_strike(report: dict[str, Any]) -> None:
    """High debris roll must emit DEBRIS_STRIKE."""
    row = _sortie_row(report, "sortie_05")
    assert any(i["code"] == "DEBRIS_STRIKE" for i in row["incidents"])


def test_relay_lost(report: dict[str, Any]) -> None:
    """Missing relay ping before close must emit RELAY_LOST."""
    row = _sortie_row(report, "sortie_06")
    finding = next(i for i in row["incidents"] if i["code"] == "RELAY_LOST")
    assert finding["entity_id"] == "LYNX"


def test_claw_jammed(report: dict[str, Any]) -> None:
    """Exact zero claw after wear must emit CLAW_JAMMED."""
    row = _sortie_row(report, "sortie_07")
    assert any(i["code"] == "CLAW_JAMMED" for i in row["incidents"])


def test_wreck_missing(report: dict[str, Any]) -> None:
    """Unknown wreck id must emit WRECK_MISSING."""
    row = _sortie_row(report, "sortie_08")
    assert any(i["code"] == "WRECK_MISSING" for i in row["incidents"])


def test_orbit_unknown(report: dict[str, Any]) -> None:
    """Launch into missing orbit must emit ORBIT_UNKNOWN."""
    row = _sortie_row(report, "sortie_09")
    finding = next(i for i in row["incidents"] if i["code"] == "ORBIT_UNKNOWN")
    assert finding["entity_id"] == "VOID"


def test_craft_dup(report: dict[str, Any]) -> None:
    """Second launch of the same craft id must emit CRAFT_DUP."""
    row = _sortie_row(report, "sortie_10")
    assert any(i["code"] == "CRAFT_DUP" for i in row["incidents"])


def test_duplicate_order_skip(report: dict[str, Any]) -> None:
    """Duplicate order_id must skip later order and still recover."""
    row = _sortie_row(report, "sortie_11")
    assert row["duplicate_orders_skipped"] == 1
    assert row["status"] == "RECOVERED"


def test_jettison_recovery(report: dict[str, Any]) -> None:
    """Jettison then restow must recover both wrecks."""
    row = _sortie_row(report, "sortie_12")
    assert row["status"] == "RECOVERED"
    assert row["wrecks_recovered"] == 2


def test_burn_scale_override(report: dict[str, Any]) -> None:
    """policy_overrides burn_scale must make GEO transfer affordable."""
    row = _sortie_row(report, "sortie_13")
    assert row["status"] == "RECOVERED"
    assert row["incidents"] == []


def test_multi_wreck(report: dict[str, Any]) -> None:
    """Single craft recovering two MEO wrecks must succeed."""
    row = _sortie_row(report, "sortie_14")
    assert row["status"] == "RECOVERED"
    assert row["wrecks_recovered"] == 2


def test_ballast_empty(report: dict[str, Any]) -> None:
    """Jettison beyond hold contents must emit BALLAST_EMPTY."""
    row = _sortie_row(report, "sortie_15")
    assert any(i["code"] == "BALLAST_EMPTY" for i in row["incidents"])


def test_sortie_timeout(report: dict[str, Any]) -> None:
    """Coast past max_ticks must emit SORTIE_TIMEOUT."""
    row = _sortie_row(report, "sortie_16")
    assert any(i["code"] == "SORTIE_TIMEOUT" for i in row["incidents"])


def test_mass_reject(report: dict[str, Any]) -> None:
    """Stow without attached wreck must emit MASS_REJECT."""
    row = _sortie_row(report, "sortie_17")
    assert any(i["code"] == "MASS_REJECT" for i in row["incidents"])


def test_multi_craft(report: dict[str, Any]) -> None:
    """Two crafts recovering separate wrecks must both finish."""
    row = _sortie_row(report, "sortie_18")
    assert row["status"] == "RECOVERED"
    assert len(row["crafts"]) == 2
    assert row["wrecks_recovered"] == 2


def test_window_edge(report: dict[str, Any]) -> None:
    """Burn exactly on close_tick must succeed."""
    row = _sortie_row(report, "sortie_19")
    assert row["status"] == "RECOVERED"
    assert row["incidents"] == []


def test_wear_override(report: dict[str, Any]) -> None:
    """policy_overrides wear_per_grapple must allow two grapples."""
    row = _sortie_row(report, "sortie_20")
    assert row["status"] == "RECOVERED"
    assert row["wrecks_recovered"] == 2
