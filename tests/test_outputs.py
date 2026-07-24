"""Domain checks for landfill methane flare triage case 0708.

Golden field values are fixed oracle expectations embedded here. The grade path
rebuilds the agent's Java sources and compares emitted pack fields to those
constants; it does not re-implement k1/k2/k3 decode, widen, or ledger logic.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
OUT = APP / "output" / "hardened_policy_pack.json"
MARGIN = 0.05
W_CAP = 1.5
SCHEMA = "hz-pack-1"

# Oracle-fixed expectations for the shipped fixtures (case 0708).
EXPECTED_CASES: dict[str, dict[str, object]] = {
    "hz01": {
        "status": "ok",
        "hex_pair": "000a0014001e00280032003c",
        "widen_digest": "ad004932ed005282a1c039345d82f6bb8af0751394ecf63063241c9da9430c40",
        "row_digest": "50844ead791e1cba6478540a3a4139c173c0464fe8ae164003798723c149dac4",
        "clf_blob_hex": "763d303b6d6f64653d726f773b68783d35302e36",
        "violations": 0,
        "cap_bound": 0.75,
        "ledger_mode": "row",
    },
    "hz02": {
        "status": "ok",
        "hex_pair": "006400c8009600fa00070008",
        "widen_digest": "96aab50168a08a6efd35ec24004f9328a3b77280dff3999a1d98a691233f0fb1",
        "row_digest": "3168c96a39960331ef63d80bba91429cd40d8f9604c162ffea66a986f6c047fb",
        "clf_blob_hex": "763d303b6d6f64653d726f773b68783d3135312e32",
        "violations": 0,
        "cap_bound": 1.5,
        "ledger_mode": "row",
    },
    "hz03": {
        "status": "ok",
        "hex_pair": "00010002000300040005000600070008",
        "widen_digest": "51287b793b0c5b567d9ec409b72a142eece218ec8d8f867ea3f07c4866b3d181",
        "row_digest": "e1bed36c63eb999fbdf7f221b9674d5cb6c1be2b4b8709b44b2e60fa6dcfd419",
        "clf_blob_hex": "763d303b6d6f64653d726f773b68783d372e33",
        "violations": 0,
        "cap_bound": 0.375,
        "ledger_mode": "row",
    },
    "hz04": {
        "status": "ok",
        "hex_pair": "0009000b000d001100130017",
        "widen_digest": "52b4ac442a93bc14e8e374033bebd10707ce53038ef895c78d62ad13bba1ee5a",
        "row_digest": "da68316a0e315f2fd4567dd8e0edf0d7a979146a29faefe723564419c1c0c2de",
        "clf_blob_hex": "763d303b6d6f64653d726f773b68783d31392e38",
        "violations": 0,
        "cap_bound": 1.8,
        "ledger_mode": "row",
    },
    "hz_tr": {
        "status": "reject",
        "hex_pair": "",
        "widen_digest": "",
        "row_digest": "",
        "clf_blob_hex": "",
        "violations": 0,
        "cap_bound": 0.0,
        "ledger_mode": "sum",
    },
    "hz_rt": {
        "status": "ok",
        "hex_pair": "00280032003c0046",
        "widen_digest": "e83117786519f9c55588cc856cf37ea84c3e7a885edf6ea4a2b42f5d52a35591",
        "row_digest": "e87ef1242ba215ea4cf2e07de6ff9f3abba036e5521344994fea4eda74c626f3",
        "clf_blob_hex": "763d303b6d6f64653d726f773b68783d36302e39",
        "violations": 0,
        "cap_bound": 0.9,
        "ledger_mode": "row",
    },
}

EXPECTED_PACK_DIGEST = "54fa8048d5ddd63b9e4830399adcd33151c3e343da5891ce6b6e9d9fd0f298fb"
HZ02_LE_MISREAD_HEX = "6400c8009600fa0000070008"
HZ_RT_WIDEN_DIGEST_NO_ROT = (
    "1e4c1fd84678ccb0a6ec31d225eea372aaceb68d921c1d9123c752187061c821"
)


def _hypot2(a: float, b: float) -> float:
    return math.sqrt(a * a + b * b)


def _rebuild() -> dict:
    subprocess.run(
        ["mvn", "-q", "-DskipTests", "package", "-Dhz.marker=/app/environment/k1"],
        cwd=APP,
        check=True,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["java", "-jar", "/app/drive/target/drive-1.0.0-shaded.jar"],
        cwd=APP,
        check=True,
    )
    return json.loads(OUT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pack() -> dict:
    return _rebuild()


def _cids() -> list[str]:
    return [ln.strip() for ln in (APP / "docs" / "cid.txt").read_text().splitlines() if ln.strip()]


def _wts() -> dict[str, tuple[float, float, float]]:
    out: dict[str, tuple[float, float, float]] = {}
    for ln in (APP / "data" / "wts.tsv").read_text().splitlines():
        if not ln or ln.startswith("cid"):
            continue
        p = ln.split("\t")
        out[p[0]] = (float(p[1]), float(p[2]), float(p[3]))
    return out


def _load_ledger(cid: str) -> list[tuple[int, float, float, float, str]]:
    import sqlite3

    con = sqlite3.connect(APP / "data" / "mx8.sqlite")
    try:
        rows = con.execute(
            "SELECT rid, v_pre, v_post, delta, col_tag FROM ledger WHERE cid=? ORDER BY rid",
            (cid,),
        ).fetchall()
        return [(int(r[0]), float(r[1]), float(r[2]), float(r[3]), str(r[4])) for r in rows]
    finally:
        con.close()


def _case_map(pack: dict) -> dict[str, dict]:
    return {c["cid"]: c for c in pack["cases"]}


def test_hz_c1_layout(pack: dict) -> None:
    """Pack schema, case ids, and required fields after rebuild."""
    assert pack["schema"] == SCHEMA
    assert isinstance(pack["cases"], list)
    assert set(_case_map(pack)) == set(_cids())
    digest = pack["pack_digest"]
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert pack["verdict"] == "green"
    assert pack["pack_digest"] == EXPECTED_PACK_DIGEST
    for c in pack["cases"]:
        for key in (
            "cid",
            "status",
            "hex_pair",
            "widen_digest",
            "row_digest",
            "clf_blob_hex",
            "violations",
            "cap_bound",
            "ledger_mode",
        ):
            assert key in c


def test_hz_c2_hex_pair(pack: dict) -> None:
    """Mixed-endian hex pairs match the closed oracle fixture set."""
    cases = _case_map(pack)
    for cid in _cids():
        expect = EXPECTED_CASES[cid]
        assert cases[cid]["status"] == expect["status"]
        assert cases[cid]["hex_pair"] == expect["hex_pair"]


def test_hz_c3_digest_rule(pack: dict) -> None:
    """Widen digests match the closed oracle fixture set."""
    cases = _case_map(pack)
    for cid in _cids():
        if EXPECTED_CASES[cid]["status"] == "reject":
            continue
        assert cases[cid]["widen_digest"] == EXPECTED_CASES[cid]["widen_digest"]


def test_hz_c4_cap_bound(pack: dict) -> None:
    """Cap bound and radii obligation hold for non-trunc cases."""
    cases = _case_map(pack)
    for cid in _cids():
        if EXPECTED_CASES[cid]["status"] == "reject":
            continue
        a, b, _c = _wts()[cid]
        bound = W_CAP * max(a, b)
        radii = _hypot2(a, b)
        assert round(float(cases[cid]["cap_bound"]), 6) == round(bound, 6)
        assert round(float(cases[cid]["cap_bound"]), 6) == round(
            float(EXPECTED_CASES[cid]["cap_bound"]), 6
        )
        assert radii <= bound + 1e-9


def test_hz_c5_overwrite(pack: dict) -> None:
    """Driver overwrite replaces a static pack on disk."""
    OUT.write_text('{"schema":"bogus","cases":[],"pack_digest":"0"*64,"verdict":"green"}\n')
    again = _rebuild()
    assert again["schema"] == SCHEMA
    assert again["verdict"] == "green"
    assert len(again["cases"]) == len(_cids())


def test_hz_c6_idempotent(pack: dict) -> None:
    """Consecutive identical rebuilds emit the same pack."""
    first = json.dumps(pack, sort_keys=True)
    second = json.dumps(_rebuild(), sort_keys=True)
    assert first == second


def test_hz_c7_coeff_mutate(pack: dict) -> None:
    """Weight table mutation changes the widen digest."""
    wts_path = APP / "data" / "wts.tsv"
    backup = wts_path.read_text(encoding="utf-8")
    try:
        lines = backup.splitlines()
        out_lines = []
        for ln in lines:
            if ln.startswith("hz01\t"):
                parts = ln.split("\t")
                parts[1] = str(float(parts[1]) + 0.35)
                out_lines.append("\t".join(parts))
            else:
                out_lines.append(ln)
        wts_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        mutated = _rebuild()
        before = _case_map(pack)["hz01"]["widen_digest"]
        after = _case_map(mutated)["hz01"]["widen_digest"]
        assert before != after
    finally:
        wts_path.write_text(backup, encoding="utf-8")
        _rebuild()


def test_hz_c8_asm_ablation(pack: dict) -> None:
    """Mixed-endian decode diverges from a pure little-endian misread."""
    cases = _case_map(pack)
    assert cases["hz02"]["hex_pair"] == EXPECTED_CASES["hz02"]["hex_pair"]
    assert cases["hz02"]["hex_pair"] != HZ02_LE_MISREAD_HEX


def test_hz_c9_tab_ablation(pack: dict) -> None:
    """Held-out rotations enlarge the widen box versus rotation-free."""
    cases = _case_map(pack)
    cid = "hz_rt"
    assert cases[cid]["widen_digest"] == EXPECTED_CASES[cid]["widen_digest"]
    assert cases[cid]["widen_digest"] != HZ_RT_WIDEN_DIGEST_NO_ROT


def test_hz_c10_blob_ablation(pack: dict) -> None:
    """CLF blob binds row mode with zero violations."""
    cases = _case_map(pack)
    for cid in _cids():
        if EXPECTED_CASES[cid]["status"] == "reject":
            continue
        c = cases[cid]
        expect = EXPECTED_CASES[cid]
        assert c["ledger_mode"] == expect["ledger_mode"]
        assert c["violations"] == expect["violations"]
        assert c["clf_blob_hex"] == expect["clf_blob_hex"]


def test_hz_c11_trunc_trap(pack: dict) -> None:
    """Truncated WARC fixture rejects and pack stays green."""
    cases = _case_map(pack)
    assert cases["hz_tr"]["status"] == "reject"
    assert pack["verdict"] == "green"


def test_hz_c12_bal_trap(pack: dict) -> None:
    """Row ledger invariants bind beyond column-sum balance."""
    cases = _case_map(pack)
    for cid in _cids():
        if EXPECTED_CASES[cid]["status"] == "reject":
            continue
        ledger = _load_ledger(cid)
        sum_pre = sum(r[1] for r in ledger)
        sum_post = sum(r[2] for r in ledger)
        assert sum_pre - sum_post >= MARGIN * len(ledger) - 1e-9
        expect = EXPECTED_CASES[cid]
        assert cases[cid]["ledger_mode"] == expect["ledger_mode"]
        assert cases[cid]["violations"] == expect["violations"]
        assert cases[cid]["row_digest"] == expect["row_digest"]


def test_hz_c13_rotation_hole_trap(pack: dict) -> None:
    """An out-of-bound held-out rotation must fail the pack verdict."""
    assert pack["verdict"] == "green"
    wts_path = APP / "data" / "wts.tsv"
    backup = wts_path.read_text(encoding="utf-8")
    try:
        lines = []
        for ln in backup.splitlines():
            if ln.startswith("hz01\t"):
                parts = ln.split("\t")
                parts[3] = "60.05"
                lines.append("\t".join(parts))
            else:
                lines.append(ln)
        wts_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        hole = _rebuild()
        assert hole["verdict"] == "fail"
    finally:
        wts_path.write_text(backup, encoding="utf-8")
        restored = _rebuild()
        assert restored["verdict"] == "green"
