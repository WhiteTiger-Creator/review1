import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
OUT = APP / "output"
BUNDLE = OUT / "lineage_bundle.json"
TRACE = OUT / "tick_trace.jsonl"
PLAY_BIN = "/app/bin/qd"
BEARING_MOD = 65536
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _rebuild_qd_engine():
    subprocess.run(
        ["make", "-C", "/app/environment", "build", "install"],
        check=True,
    )


def _load_fixture_bundle(stem: str) -> dict:
    return json.loads((FIXTURES / f"{stem}.bundle.json").read_text(encoding="utf-8"))


def _load_fixture_trace(stem: str) -> list[dict]:
    rows = []
    path = FIXTURES / f"{stem}.trace.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _digest_from_lines(lines: list[dict]) -> str:
    parts = []
    for row in lines:
        parts.append(
            f"{row['seq']}|{row['label']}|{row['bearing']}|{row['slot_idx']}|{row['seg_crc']}"
        )
    parts.sort()
    payload = "\n".join(parts)
    mask64 = (1 << 64) - 1
    total = 0
    for i, ch in enumerate(payload):
        addend = ((i + 1) * ord(ch)) & mask64
        total = (total + addend) & mask64
    return f"{total & 0xFFFFFFFF:08x}"


def _read_trace() -> list[dict]:
    rows = []
    for line in TRACE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _play(lane: Path) -> dict:
    subprocess.run(
        [PLAY_BIN, "play", "--lane", str(lane)],
        check=True,
        cwd=str(APP),
    )
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def _bearing_in_span(rows: list[dict]) -> bool:
    return all(0 <= r["bearing"] < BEARING_MOD for r in rows)


def test_h7_k1_anchor():
    """Primary m3 lane tick_digest and entity_rows match contract goldens."""
    expected = _load_fixture_bundle("m3")
    bundle = _play(APP / "w8" / "d7" / "m3.lane")
    rows = _read_trace()
    assert bundle["tick_digest"] == expected["tick_digest"]
    assert bundle["tick_digest"] == _digest_from_lines(rows)
    assert list(bundle["entity_rows"]) == expected["entity_rows"]
    assert bundle["line_count"] == len(rows)


def test_h7_k2_deep():
    """Deep m3 lane produces more trace lines than shallow z1."""
    shallow = _play(APP / "w8" / "d7" / "z1.lane")
    deep = _play(APP / "w8" / "d7" / "m3.lane")
    z1_golden = _load_fixture_bundle("z1")
    assert shallow["line_count"] == z1_golden["line_count"]
    assert deep["line_count"] > shallow["line_count"]
    assert deep["tick_digest"] != shallow["tick_digest"]


def test_h7_k3_mux():
    """z2 lane tick_digest stable when dup frames are retained."""
    expected = _load_fixture_bundle("z2")
    bundle = _play(APP / "w8" / "d7" / "z2.lane")
    rows = _read_trace()
    assert bundle["tick_digest"] == expected["tick_digest"]
    assert bundle["tick_digest"] == _digest_from_lines(rows)
    assert bundle["line_count"] >= 4


def test_h7_k4_swap():
    """z2 lane satisfies bearing span and digest recompute."""
    expected = _load_fixture_bundle("z2")
    bundle = _play(APP / "w8" / "d7" / "z2.lane")
    rows = _read_trace()
    assert _bearing_in_span(rows)
    assert bundle["tick_digest"] == expected["tick_digest"]
    assert bundle["tick_digest"] == _digest_from_lines(rows)


def test_h7_k5_scan():
    """Scan succeeds on z1 only; m3 play still matches golden tick_digest."""
    scan_z1 = subprocess.run(
        [PLAY_BIN, "scan", "--lane", str(APP / "w8" / "d7" / "z1.lane")],
        cwd=str(APP),
        capture_output=True,
        text=True,
        check=False,
    )
    assert scan_z1.returncode == 0
    assert scan_z1.stdout.strip() == "z1:0"
    scan_m3 = subprocess.run(
        [PLAY_BIN, "scan", "--lane", str(APP / "w8" / "d7" / "m3.lane")],
        cwd=str(APP),
        capture_output=True,
        text=True,
        check=False,
    )
    assert scan_m3.returncode != 0
    assert scan_m3.stdout.strip() == "m3:2"
    expected = _load_fixture_bundle("m3")
    bundle = _play(APP / "w8" / "d7" / "m3.lane")
    rows = _read_trace()
    assert bundle["tick_digest"] == expected["tick_digest"]
    assert bundle["tick_digest"] == _digest_from_lines(rows)


def test_h7_k6_mux():
    """m3 trace bearings stay within the contract fold range on every line."""
    _play(APP / "w8" / "d7" / "m3.lane")
    rows = _read_trace()
    assert _bearing_in_span(rows)


def test_h7_k7_pair():
    """Back-to-back m3 plays yield identical tick_digest and entity_rows."""
    first = _play(APP / "w8" / "d7" / "m3.lane")
    rows1 = _read_trace()
    second = _play(APP / "w8" / "d7" / "m3.lane")
    rows2 = _read_trace()
    assert first["tick_digest"] == second["tick_digest"]
    assert first["entity_rows"] == second["entity_rows"]
    assert _digest_from_lines(rows1) == _digest_from_lines(rows2)


def test_h7_k8_plant():
    """Live play overwrites a planted bundle JSON file."""
    fake = {
        "lane_id": "m3",
        "tick_digest": "00000000",
        "entity_rows": [0] * 8,
        "line_count": 0,
    }
    BUNDLE.write_text(json.dumps(fake), encoding="utf-8")
    live = _play(APP / "w8" / "d7" / "m3.lane")
    assert live["lane_id"] == "m3"
    assert live["tick_digest"] != "00000000"


def test_h7_k9_hold():
    """Held-out x4 lanes satisfy golden digest and entity_rows like m3."""
    for stem in ("x4_01", "x4_02"):
        expected = _load_fixture_bundle(stem)
        bundle = _play(APP / "w8" / "d7" / f"{stem}.lane")
        rows = _read_trace()
        assert bundle["line_count"] == len(rows)
        assert bundle["tick_digest"] == expected["tick_digest"]
        assert list(bundle["entity_rows"]) == expected["entity_rows"]
        assert bundle["tick_digest"] != "00000000"
