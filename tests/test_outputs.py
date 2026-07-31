"""Behavioral checks for training/serving skew journal."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ENV = Path("/app/environment")
OUT = Path("/app/output/skew_journal.json")
TOL = 1e-9
K = 0x9E3779B97F4A7C15


def _fnv_u64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def _hex16(v: int) -> str:
    return f"{v:016x}"


def _f32_pack(value: float) -> bytes:
    # NaN is the only float that is unordered with 0 and both signs.
    if not (value < 0.0 or value > 0.0 or value == 0.0):
        return (0x7FC00000).to_bytes(4, "little")
    if value == float("inf"):
        return (0x7F800000).to_bytes(4, "little")
    if value == float("-inf"):
        return (0xFF800000).to_bytes(4, "little")
    sign = 1 if (value < 0.0 or (value == 0.0 and str(value).startswith("-"))) else 0
    if value == 0.0:
        return (sign << 31).to_bytes(4, "little")
    abs_v = -value if value < 0 else value
    exp = 0
    while abs_v >= 1.0:
        abs_v *= 0.5
        exp += 1
    while abs_v < 0.5:
        abs_v *= 2.0
        exp -= 1
    exp_bits = exp + 126
    if exp_bits >= 255:
        return ((sign << 31) | 0x7F800000).to_bytes(4, "little")
    if exp_bits <= 0:
        frac = int(abs_v * float(1 << (23 + exp_bits)))
        return ((sign << 31) | (frac & 0x7FFFFF)).to_bytes(4, "little")
    frac = int((abs_v * 2.0 - 1.0) * float(1 << 23) + 0.5)
    return ((sign << 31) | ((exp_bits & 0xFF) << 23) | (frac & 0x7FFFFF)).to_bytes(4, "little")


def _f32_at(buf: bytes, off: int) -> float:
    bits = int.from_bytes(buf[off : off + 4], "little")
    sign = -1.0 if (bits >> 31) else 1.0
    exp_bits = (bits >> 23) & 0xFF
    frac = bits & 0x7FFFFF
    if exp_bits == 255:
        return float("inf") * sign if frac == 0 else float("nan")
    if exp_bits == 0:
        if frac == 0:
            return 0.0 * sign
        return sign * (float(frac) * (2.0**-149))
    return sign * ((1.0 + float(frac) / float(1 << 23)) * (2.0 ** (exp_bits - 127)))


def _load_slots(rel: str):
    obj = json.loads((ENV / rel).read_text(encoding="utf-8"))
    return [(s["name"], float(s["v"])) for s in obj.get("slots", [])]


def _resolve_wire(gen: int, wire: str):
    maps = {
        0: {"u_a": "u_a", "u_b": "u_b", "u_c": "u_c", "u_d": "u_d"},
        1: {"v_a": "u_a", "v_c": "u_c", "u_b": "u_b", "u_d": "u_d"},
        2: {
            "u_a": "u_a",
            "u_b": "u_b",
            "w_n": "w_n",
            "u_c": "u_c",
            "u_d": "u_d",
        },
        3: {"u_a": "u_a", "u_b": "u_b", "u_d": "u_d"},
    }
    canon = (
        ["u_a", "u_b", "w_n", "u_c", "u_d"]
        if gen >= 2 and gen != 3
        else ["u_a", "u_b", "u_c", "u_d"]
    )
    m = maps.get(gen, {})
    if wire in m:
        return m[wire]
    if wire in m.values() or wire in canon:
        return wire
    if gen in maps:
        return None
    if wire in canon:
        return wire
    return None


def _canon(gen: int):
    if gen >= 2 and gen != 3:
        return ["u_a", "u_b", "w_n", "u_c", "u_d"]
    return ["u_a", "u_b", "u_c", "u_d"]


def _bind_fill(gen: int, slots):
    resolved = {}
    for w, v in slots:
        c = _resolve_wire(gen, w)
        if c is None:
            return None
        resolved[c] = v
    names = _canon(gen)
    fills = {"w_n": 0.125}
    out = bytearray()
    present = []
    for n in names:
        if n in resolved:
            out += _f32_pack(resolved[n])
            present.append(True)
        elif n in fills:
            out += _f32_pack(fills[n])
            present.append(True)
        else:
            out += _f32_pack(0.0)
            present.append(False)
    for name in ["u_c"]:
        idx = names.index(name) if name in names else -1
        if idx < 0 or not present[idx]:
            return b""
    for name in names:
        idx = names.index(name)
        if not present[idx]:
            return b""
    return bytes(out)


def _baseline_u64(slots) -> int:
    mapped = []
    for w, v in slots:
        n = w
        if n == "v_a":
            n = "u_a"
        elif n == "v_c":
            n = "u_c"
        if n == "w_n":
            continue
        mapped.append((n, v))
    b = _bind_fill(0, mapped)
    assert b is not None and b != b""
    return _fnv_u64(b)


def _expect_preds(chan: bytes, base_u: int):
    d = _fnv_u64(chan)
    h = (d ^ ((base_u * K) & 0xFFFFFFFFFFFFFFFF)) & 0xFFFFFFFFFFFFFFFF
    rows = []
    for i in range(1, 4):
        mixed = (h + i * 17) & 0xFFFFFFFFFFFFFFFF
        v = 1.0 / (1.0 + (mixed % 1000) / 100.0)
        rows.append((i, v))
    return rows


def _near(a: float, b: float) -> bool:
    d = a - b
    if d < 0:
        d = -d
    return d < TOL


def _preds_ok(arm: dict, chan: bytes, slots) -> bool:
    expect = _expect_preds(chan, _baseline_u64(slots))
    if arm["gate_code"] != 0 or len(arm["pred_rows"]) != 3:
        return False
    for (t, v), row in zip(expect, arm["pred_rows"]):
        if row["t"] != t or not _near(row["v"], v):
            return False
    return True


def _journal_blob() -> dict:
    subprocess.run(
        ["/app/environment/scripts/refresh_join.sh"],
        check=True,
        cwd="/app/environment",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "/app/environment/tools/skew_probe/skew_probe",
            "--suite",
            "full",
            "--catalog",
            "/app/environment/cfgs/join_policy.toml",
            "--journal-out",
            "/app/output/skew_journal.json",
        ],
        check=True,
    )
    return json.loads(OUT.read_text(encoding="utf-8"))


def _rev_row(blob: dict, rev_id: str) -> dict:
    for a in blob["rev_traces"]:
        if a["rev_id"] == rev_id:
            return a
    raise AssertionError(f"missing rev {rev_id}")


def _edge_row(blob: dict, rev_id: str) -> dict:
    for a in blob["edge_traces"]:
        if a["rev_id"] == rev_id:
            return a
    raise AssertionError(f"missing edge {rev_id}")


@pytest.fixture(scope="module")
def journal() -> dict:
    return _journal_blob()


class TestJSuiteA:
    def test_j01(self, journal: dict):
        """Renamed wire names keep channel digests aligned with the baseline revision."""
        base = _rev_row(journal, "rev_base")
        ren = _rev_row(journal, "rev_rename")
        assert ren["gate_code"] == 0
        assert ren["offline_geom"] == base["offline_geom"] == ren["online_geom"]
        assert ren["chan_digest"] == base["chan_digest"]

    def test_j02(self, journal: dict):
        """Shuffled slot order on an edge fixture still matches the baseline digest."""
        base = _rev_row(journal, "rev_base")
        edge = _edge_row(journal, "edge_reorder")
        assert edge["gate_code"] == 0
        assert edge["chan_digest"] == base["chan_digest"]

    def test_j03(self, journal: dict):
        """Partially remapped edge wires resolve to the same baseline digest."""
        base = _rev_row(journal, "rev_base")
        edge = _edge_row(journal, "edge_mixed")
        assert edge["gate_code"] == 0
        assert edge["chan_digest"] == base["chan_digest"]


class TestJSuiteB:
    def test_j04(self, journal: dict):
        """Additive nullable revision keeps offline and online digests identical."""
        arm = _rev_row(journal, "rev_add")
        slots = _load_slots("fixtures/revs/add.json")
        expect = _bind_fill(2, slots)
        assert arm["gate_code"] == 0 and arm["offline_geom"] == arm["online_geom"]
        assert expect is not None and expect != b""
        assert arm["chan_digest"] == _hex16(_fnv_u64(expect))

    def test_j05(self, journal: dict):
        """Missing nullable slot receives the documented public default value."""
        slots = _load_slots("fixtures/revs/add.json")
        expect = _bind_fill(2, slots)
        arm = _rev_row(journal, "rev_add")
        assert expect is not None and _near(_f32_at(expect, 8), 0.125)
        assert arm["chan_digest"] == _hex16(_fnv_u64(expect))


class TestJSuiteC:
    def test_j06(self, journal: dict):
        """Forbidden removal revision hard-fails with empty prediction rows."""
        arm = _rev_row(journal, "rev_drop")
        assert arm["gate_code"] == 2
        assert arm["pred_rows"] == [] and arm["chan_digest"] == ""

    def test_j07(self, journal: dict):
        """Empty boundary fixture hard-fails the same way as a forbidden removal."""
        edge = _edge_row(journal, "edge_empty")
        assert edge["gate_code"] == 2
        assert edge["pred_rows"] == []

    def test_j08(self, journal: dict):
        """Baseline revision still scores successfully when other revisions reject."""
        base = _rev_row(journal, "rev_base")
        assert base["gate_code"] == 0
        assert len(base["pred_rows"]) == 3


class TestJSuiteD:
    def test_j09(self, journal: dict):
        """Baseline prediction rows stay continuous with the documented mix."""
        arm = _rev_row(journal, "rev_base")
        slots = _load_slots("fixtures/revs/base.json")
        chan = _bind_fill(0, slots)
        assert chan is not None and chan != b""
        assert _preds_ok(arm, chan, slots)

    def test_j10(self, journal: dict):
        """Alternate baseline payload still follows the same continuity mix."""
        arm = _rev_row(journal, "rev_twice")
        slots = _load_slots("fixtures/revs/twice.json")
        chan = _bind_fill(0, slots)
        assert chan is not None and chan != b""
        assert _preds_ok(arm, chan, slots)

    def test_j11(self, journal: dict):
        """Replay rows from an identical second run match the first accepted predictions."""
        first = next(a for a in journal["rev_traces"] if a["gate_code"] == 0)
        assert journal["replay_rows"] == first["pred_rows"]
