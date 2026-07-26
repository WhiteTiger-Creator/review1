"""Verifier for federation consumer-trust cutover authorization."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
OUT = APP / "output" / "trust_report.json"
BUILD = APP / "scripts" / "build.sh"
BIN = APP / "bin" / "trust_desk"
PACK = APP / "data" / "scenario_pack.json"
PROBE = APP / "scripts" / "local_probe.sh"
PAIR_INDEX = APP / "data" / "corpus" / "pair_index.json"
WINDOW_TABLE = APP / "data" / "anchors" / "window_table.json"
REVOKE_LEDGER = APP / "data" / "anchors" / "revoke_ledger.json"
GRACE_TABLE = APP / "data" / "cache" / "grace_table.json"

EXPECTED_OUTCOME = {
    "m_alpha": "allow",
    "m_beta": "deny",
    "m_gamma": "deny",
    "m_delta": "allow",
    "m_epsilon": "deny",
    "m_zeta": "allow",
}


def digest_for(scenario_id: str, outcome: str) -> str:
    payload = f"{scenario_id}|{outcome}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def run_checked(cmd: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def rebuild_and_run() -> dict:
    run_checked(["bash", str(BUILD)], timeout=180)
    out_dir = APP / "output"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_checked(
        [str(BIN), "--pack", str(PACK), "--out", str(out_dir), "--root", str(APP)],
        timeout=120,
    )
    return json.loads(OUT.read_text(encoding="utf-8"))


def assert_row(doc: dict, sid: str) -> None:
    row = doc["scenarios"][sid]
    want_outcome = EXPECTED_OUTCOME[sid]
    want_digest = digest_for(sid, want_outcome)
    assert row["outcome"] == want_outcome, sid
    assert row["matrix_digest"] == want_digest, sid


def assert_full_matrix(doc: dict) -> None:
    for sid in EXPECTED_OUTCOME:
        assert_row(doc, sid)


@pytest.fixture(scope="session")
def matrix() -> dict:
    return rebuild_and_run()


def test_m_alpha_fields(matrix: dict) -> None:
    """m_alpha mid-rollover pairing is authorized allow with matching digest."""
    assert_row(matrix, "m_alpha")


def test_m_beta_fields(matrix: dict) -> None:
    """m_beta digest-without-parent bait stays refused with matching digest."""
    assert_row(matrix, "m_beta")


def test_m_gamma_fields(matrix: dict) -> None:
    """m_gamma post-cutover revoke stays refused with matching digest."""
    assert_row(matrix, "m_gamma")


def test_m_delta_fields(matrix: dict) -> None:
    """m_delta dual-generation mid-window stays authorized allow with matching digest."""
    assert_row(matrix, "m_delta")


def test_m_epsilon_fields(matrix: dict) -> None:
    """m_epsilon clock-grace stickiness keeps refuse with matching digest."""
    assert_row(matrix, "m_epsilon")


def test_m_zeta_fields(matrix: dict) -> None:
    """m_zeta past-grace freshness yields authorized allow with matching digest."""
    assert_row(matrix, "m_zeta")


def test_shape_contract(matrix: dict) -> None:
    """schema_version and required keys hold; signer-view probe stays clean."""
    assert matrix["schema_version"] == "2"
    assert set(matrix["scenarios"]) == set(EXPECTED_OUTCOME)
    for sid, row in matrix["scenarios"].items():
        assert set(row) == {"outcome", "matrix_digest"}
        assert row["outcome"] in ("allow", "deny")
        assert len(row["matrix_digest"]) == 16
        assert_row(matrix, sid)
    probe = run_checked(["bash", str(PROBE)], timeout=30)
    assert "PROBE ok" in probe.stdout


def test_ablation_pairing_surface(matrix: dict) -> None:
    """Corrupting pair bindings regresses pairing rows; other surfaces stay authorized."""
    assert_full_matrix(matrix)
    backup = PAIR_INDEX.read_bytes()
    try:
        PAIR_INDEX.write_text(
            json.dumps(
                {
                    "pairs": {
                        "r_old": "p_old",
                        "r_new": "WRONG",
                        "r_bait": "",
                        "p_g": "p_g",
                        "p_d": "p_d",
                        "p_e": "p_e",
                        "p_z": "p_z",
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        doc = rebuild_and_run()
        assert doc["scenarios"]["m_alpha"]["outcome"] != EXPECTED_OUTCOME["m_alpha"]
        assert_row(doc, "m_beta")
        assert_row(doc, "m_gamma")
        assert_row(doc, "m_delta")
        assert_row(doc, "m_epsilon")
        assert_row(doc, "m_zeta")
    finally:
        PAIR_INDEX.write_bytes(backup)
        rebuild_and_run()


def test_ablation_generation_surface(matrix: dict) -> None:
    """Corrupting window/revoke tables regresses generation rows; other surfaces stay authorized."""
    assert_full_matrix(matrix)
    win_backup = WINDOW_TABLE.read_bytes()
    rev_backup = REVOKE_LEDGER.read_bytes()
    try:
        wins = json.loads(win_backup)
        wins["slots"]["p_d"] = {"legacy": 1, "tip": 3, "dual": True, "a": 9, "b": 9}
        wins["slots"]["p_g"] = {"legacy": 3, "tip": 3, "dual": False, "a": 0, "b": 0}
        WINDOW_TABLE.write_text(json.dumps(wins) + "\n", encoding="utf-8")
        rev = json.loads(rev_backup)
        rev["gone"]["p_g"] = {}
        REVOKE_LEDGER.write_text(json.dumps(rev) + "\n", encoding="utf-8")
        doc = rebuild_and_run()
        assert doc["scenarios"]["m_gamma"]["outcome"] != EXPECTED_OUTCOME["m_gamma"]
        assert doc["scenarios"]["m_delta"]["outcome"] != EXPECTED_OUTCOME["m_delta"]
        assert_row(doc, "m_alpha")
        assert_row(doc, "m_beta")
        assert_row(doc, "m_epsilon")
        assert_row(doc, "m_zeta")
    finally:
        WINDOW_TABLE.write_bytes(win_backup)
        REVOKE_LEDGER.write_bytes(rev_backup)
        rebuild_and_run()


def test_ablation_polarity_surface(matrix: dict) -> None:
    """Corrupting grace polarity regresses grace rows; other surfaces stay authorized."""
    assert_full_matrix(matrix)
    backup = GRACE_TABLE.read_bytes()
    try:
        grace = json.loads(backup)
        for sid in ("m_epsilon", "m_zeta"):
            row = grace["rows"][sid]
            row["held"], row["next"] = row["next"], row["held"]
        GRACE_TABLE.write_text(json.dumps(grace) + "\n", encoding="utf-8")
        doc = rebuild_and_run()
        assert doc["scenarios"]["m_epsilon"]["outcome"] != EXPECTED_OUTCOME["m_epsilon"]
        assert doc["scenarios"]["m_zeta"]["outcome"] != EXPECTED_OUTCOME["m_zeta"]
        assert_row(doc, "m_alpha")
        assert_row(doc, "m_beta")
        assert_row(doc, "m_gamma")
        assert_row(doc, "m_delta")
    finally:
        GRACE_TABLE.write_bytes(backup)
        rebuild_and_run()
