import json
import os
import re
import struct
import subprocess
import time
from pathlib import Path

import pytest

APP = Path("/app")
ENV = APP / "environment"
OUT = APP / "output"
REPORT = OUT / "span_transcript.json"
JOURNAL = OUT / "span.journal"
MANIFEST = ENV / "data" / "order_list.toml"
UNITS = ENV / "data" / "units"
CACHE = ENV / "var" / "object_cache"
BUDGET = ENV / "data" / "gen_limit.toml"
STAMP = ENV / "var" / "gen.stamp"
PAIR = ENV / "data" / "ref_h0.toml"
FENCE = ENV / "var" / "arc.fence"
CARRY = ENV / "var" / "carry.side"
AR_INDEX = ENV / "var" / "ar.index"
TOL = 1e-5

FORBIDDEN_LINK_TARGETS = {
    "dig_fold": ENV / "src" / "lib_wire.cmake",
    "pol_gate": ENV / "src" / "lib_wire.cmake",
    "wal_io": ENV / "src" / "lib_wire.cmake",
    "obj_stage": ENV / "src" / "lib_wire.cmake",
    "ix_pack": ENV / "src" / "lib_wire.cmake",
    "era_clk": ENV / "src" / "lib_wire.cmake",
    "layer_emit": ENV / "bx" / "bin_wire.cmake",
    "yseal": ENV / "bx" / "bin_wire.cmake",
}


def _rerun_chain():
    REPORT.unlink(missing_ok=True)
    JOURNAL.unlink(missing_ok=True)
    subprocess.run(["/app/environment/tools/run_emit_chain.sh"], cwd="/app", check=True)
    return json.loads(REPORT.read_text())


def _chain_keep_journal():
    REPORT.unlink(missing_ok=True)
    subprocess.run(["/app/environment/tools/run_emit_chain.sh"], cwd="/app", check=True)
    return json.loads(REPORT.read_text())


def _yseal():
    subprocess.run(
        [
            "/app/environment/build/cmd/yseal/yseal",
            "--journal",
            "/app/output/span.journal",
            "--report",
            "/app/output/span_transcript.json",
        ],
        cwd="/app",
        check=True,
    )


@pytest.fixture(scope="module", autouse=True)
def rebuilt_outputs():
    OUT.mkdir(exist_ok=True)
    STAMP.write_text("3\n")
    FENCE.write_text("gen=3 digest=cafebabecafebabe\n")
    CARRY.write_text("00000000\n")
    _rerun_chain()


def _names():
    raw = MANIFEST.read_text()
    body = raw[raw.index("[") + 1 : raw.index("]")]
    return [x.strip().strip('"') for x in body.split(",") if x.strip()]


def _read_pair():
    raw = PAIR.read_text()
    return raw.split('"')[1]


def _read_budget():
    return int(BUDGET.read_text().split("=")[1].strip())


def _read_stamp():
    return int(STAMP.read_text().strip())


def _read_fence():
    line = FENCE.read_text().strip()
    parts = dict(p.split("=", 1) for p in line.split())
    return int(parts["gen"]), parts["digest"]


def _fnv(raw: bytes) -> int:
    h = 2166136261
    for b in raw:
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _hex16(v: int) -> str:
    return f"{v:016x}"


def _hex8(v: int) -> str:
    return f"{v:08x}"


def _live_unit_bytes(base=UNITS):
    return [Path(base, n).read_bytes() for n in _names()]


def _probe_from(base=UNITS):
    return sum(struct.unpack("<f", raw[:4])[0] for raw in _live_unit_bytes(base))


def _content_hex(raw: bytes) -> str:
    return _hex16(_fnv(raw))


def _index_hex(blobs=None, gen=None):
    if blobs is None:
        blobs = _live_unit_bytes()
    if gen is None:
        gen = _read_budget()
    lines = []
    for name, raw in zip(_names(), blobs):
        lines.append(f"{name} {_content_hex(raw)} {gen}")
    body = "\n".join(lines)
    return _hex16(_fnv(bytes(body, "ascii"))), body


def _unit_digest(c=None, base=UNITS, index=None):
    if c is None:
        c = _read_budget()
    blobs = _live_unit_bytes(base)
    if index is None:
        index, _ = _index_hex(blobs, c)
    raw = (
        b"".join(blobs)
        + struct.pack("<i", c)
        + struct.pack("<i", len(blobs))
        + bytes(index, "ascii")
    )
    return _hex16(_fnv(raw))


def _bind_hex(a=None, b=None):
    if a is None:
        a = _unit_digest()
    if b is None:
        b = _read_pair()
    return _hex16(_fnv(bytes(a, "ascii") + bytes(b, "ascii")))


def _span_tag(digest, carry, gen):
    return _hex8(_fnv(bytes(digest, "ascii") + bytes(carry, "ascii") + struct.pack("<i", gen)))


def _crc32_iso(raw: bytes) -> int:
    c = 0xFFFFFFFF
    for b in raw:
        c ^= b
        for _ in range(8):
            if c & 1:
                c = (c >> 1) ^ 0xEDB88320
            else:
                c >>= 1
            c &= 0xFFFFFFFF
    return c ^ 0xFFFFFFFF


def _parse_journal():
    raw = JOURNAL.read_bytes()
    assert raw[:4] == b"SPJ2"
    off = 4
    g, n = struct.unpack_from("<ii", raw, off)
    off += 8
    unit_blobs = []
    for _ in range(n):
        (size,) = struct.unpack_from("<i", raw, off)
        off += 4
        unit_blobs.append(raw[off : off + size])
        off += size
    (psum,) = struct.unpack_from("<f", raw, off)
    off += 4
    digest = raw[off : off + 16].decode()
    off += 16
    pair = raw[off : off + 16].split(b"\0", 1)[0].decode()
    off += 16
    body = raw[4:off]
    (wcrc,) = struct.unpack_from("<I", raw, off)
    off += 4
    (trailer,) = struct.unpack_from("<i", raw, off)
    return g, n, unit_blobs, psum, digest, pair, body, wcrc, trailer


def _crc_probe_link_hits(text: str) -> list[str]:
    return re.findall(r"target_link_libraries\s*\([^)]*\bcrc_probe\b", text, re.DOTALL)


def _poison_cache_newer():
    """Make cache files newer than live with mismatched content."""
    for n in _names():
        live = UNITS / n
        cache = CACHE / n
        # Valid LE float32 far from live probe contributions, plus distinct bytes.
        cache.write_bytes(struct.pack("<f", 99.0) + bytes(n, "ascii") + b"-stale-cache-pad")
        # Ensure cache mtime is strictly newer than live.
        now = time.time() + 5
        os.utime(cache, (now, now))
        os.utime(live, (now - 30, now - 30))


def test_active_generation_aligns_ceiling():
    """A normal run refreshes a stale generation stamp to the budget on both surfaces."""
    STAMP.write_text("3\n")
    data = _rerun_chain()
    expected = _read_budget()
    idx, _ = _index_hex(gen=expected)
    assert data["gen_epoch"] == expected
    assert data["stamp_epoch"] == expected
    assert _read_stamp() == expected
    assert data["carry_hex"] == "00000000"
    assert data["index_hex"] == idx
    assert data["unit_digest"] == _unit_digest(expected, index=idx)
    assert data["span_tag"] == _span_tag(data["unit_digest"], data["carry_hex"], data["gen_epoch"])


def test_cache_mtime_poison_prefers_live_content():
    """Newer mismatched cache blobs must not win over live unit bytes."""
    STAMP.write_text("3\n")
    _poison_cache_newer()
    data = _rerun_chain()
    idx, _ = _index_hex(gen=data["gen_epoch"])
    assert data["index_hex"] == idx
    assert data["unit_digest"] == _unit_digest(data["gen_epoch"], UNITS, idx)
    assert data["unit_digest"] != _unit_digest(data["gen_epoch"], CACHE)
    live_probe = _probe_from(UNITS)
    cache_probe = _probe_from(CACHE)
    delta_live = abs(data["probe_sum"] - live_probe)
    delta_cache = abs(data["probe_sum"] - cache_probe)
    assert delta_live <= TOL
    assert delta_cache > 1.0
    fgen, fdig = _read_fence()
    assert fgen == data["gen_epoch"]
    assert fdig == data["index_hex"]


def test_ceiling_raise_advances_active_and_zeros_carry():
    """Raising the budget advances generation, rewrites fence to index_hex, and zeros carry."""
    old_budget = BUDGET.read_text()
    old_stamp = STAMP.read_text()
    try:
        _rerun_chain()
        prior = json.loads(REPORT.read_text())
        bumped = _read_budget() + 4
        BUDGET.write_text(f"gen_epoch = {bumped}\n")
        data = _chain_keep_journal()
        idx, body = _index_hex(gen=bumped)
        assert data["gen_epoch"] == bumped
        assert data["stamp_epoch"] == bumped
        assert _read_stamp() == bumped
        assert data["carry_hex"] == "00000000"
        assert data["index_hex"] == idx
        assert data["wal_crc"] != prior["wal_crc"] or data["unit_digest"] != prior["unit_digest"]
        fgen, fdig = _read_fence()
        assert fgen == bumped
        assert fdig == idx
        assert AR_INDEX.read_text().startswith(body.split("\n")[0])
        assert data["span_tag"] == _span_tag(data["unit_digest"], "00000000", bumped)
    finally:
        BUDGET.write_text(old_budget)
        STAMP.write_text(old_stamp)
        _rerun_chain()


def test_carry_requires_fence_index_agreement_across_payload_edit():
    """Same-gen re-emit carries prior wal_crc only when fence index_hex still agrees."""
    STAMP.write_text("3\n")
    first = _rerun_chain()
    old_crc = first["wal_crc"]
    assert first["carry_hex"] == "00000000"
    fgen, fdig = _read_fence()
    assert fgen == first["gen_epoch"]
    assert fdig == first["index_hex"]
    p = UNITS / "u1.bin"
    old = p.read_bytes()
    try:
        changed = bytearray(old)
        changed[-1] ^= 0x23
        p.write_bytes(bytes(changed))
        second = _chain_keep_journal()
        idx2, _ = _index_hex(gen=second["gen_epoch"])
        assert second["index_hex"] == idx2
        assert second["index_hex"] != first["index_hex"]
        assert second["carry_hex"] == old_crc
        assert second["wal_crc"] != old_crc
        assert second["unit_digest"] == _unit_digest(second["gen_epoch"], index=idx2)
        assert second["gen_epoch"] == first["gen_epoch"]
        assert second["span_tag"] == _span_tag(
            second["unit_digest"], second["carry_hex"], second["gen_epoch"]
        )
        fgen2, fdig2 = _read_fence()
        assert fgen2 == second["gen_epoch"]
        assert fdig2 == second["index_hex"]
    finally:
        p.write_bytes(old)
        _rerun_chain()


def test_stale_fence_zeros_carry_even_with_matching_journal():
    """A journal at the active generation does not carry when arc.fence index disagrees."""
    STAMP.write_text("3\n")
    first = _rerun_chain()
    assert first["carry_hex"] == "00000000"
    FENCE.write_text(f"gen={first['gen_epoch']} digest=deadbeefdeadbeef\n")
    second = _chain_keep_journal()
    assert second["gen_epoch"] == first["gen_epoch"]
    assert second["carry_hex"] == "00000000"
    assert second["span_tag"] == _span_tag(second["unit_digest"], "00000000", second["gen_epoch"])


def test_carry_zero_when_journal_gen_mismatches():
    """carry_hex is 00000000 when an existing journal gen_epoch differs from active."""
    STAMP.write_text("3\n")
    first = _rerun_chain()
    assert first["carry_hex"] == "00000000"
    raw = bytearray(JOURNAL.read_bytes())
    foreign = first["gen_epoch"] + 99
    raw[4:8] = struct.pack("<i", foreign)
    raw[-4:] = struct.pack("<i", foreign)
    body = bytes(raw[4:-8])
    raw[-8:-4] = struct.pack("<I", _crc32_iso(body))
    JOURNAL.write_bytes(bytes(raw))
    second = _chain_keep_journal()
    assert second["gen_epoch"] == first["gen_epoch"]
    assert second["carry_hex"] == "00000000"
    idx, _ = _index_hex(gen=second["gen_epoch"])
    assert second["unit_digest"] == _unit_digest(second["gen_epoch"], index=idx)


def test_content_hash_follows_sequence_count_index_and_active():
    """The unit digest follows manifest bytes, active generation, unit_count, and index_hex."""
    data = _rerun_chain()
    idx, _ = _index_hex(gen=data["gen_epoch"])
    expected = _unit_digest(data["gen_epoch"], index=idx)
    no_index = _hex16(
        _fnv(
            b"".join(_live_unit_bytes())
            + struct.pack("<i", data["gen_epoch"])
            + struct.pack("<i", len(_names()))
        )
    )
    reverse = _hex16(
        _fnv(
            b"".join(reversed(_live_unit_bytes()))
            + struct.pack("<i", data["gen_epoch"])
            + struct.pack("<i", len(_names()))
            + bytes(idx, "ascii")
        )
    )
    assert data["index_hex"] == idx
    assert data["unit_digest"] == expected
    assert data["unit_digest"] != no_index
    assert data["unit_digest"] != reverse
    assert data["mesh_id"] == _bind_hex(expected, "h0")


def test_class_follows_nibble_and_alignment():
    """seal_class follows the documented open/hold rule on the live digest."""
    data = _rerun_chain()
    idx, _ = _index_hex(gen=data["gen_epoch"])
    live = _unit_digest(data["gen_epoch"], index=idx)
    nib = int(live[-1], 16)
    expect = (
        "mesh_open_t"
        if (nib % 2 == 1 and data["gen_epoch"] == data["stamp_epoch"])
        else "mesh_hold_t"
    )
    assert data["unit_digest"] == live
    assert data["seal_class"] == expect


def test_score_sum_from_live_payloads():
    """The probe sum comes from live units, not the object cache."""
    _poison_cache_newer()
    data = _rerun_chain()
    live_probe = _probe_from(UNITS)
    cache_probe = _probe_from(CACHE)
    delta_live = abs(data["probe_sum"] - live_probe)
    delta_cache = abs(data["probe_sum"] - cache_probe)
    assert delta_live <= TOL
    assert delta_cache > 1.0


def test_journal_checksum_trailer_reseal():
    """A valid journal reseals with matching CRC, trailer, fence index, carry.side, and span_tag."""
    data = _rerun_chain()
    gen, count, unit_blobs, psum, digest, pair, body, wcrc, trailer = _parse_journal()
    probe = data["probe_sum"]
    assert gen == data["gen_epoch"]
    assert count == data["unit_count"]
    assert unit_blobs == _live_unit_bytes()
    assert abs(psum - probe) <= TOL
    assert digest == data["unit_digest"]
    assert pair == data["pair_ref"]
    assert wcrc == _crc32_iso(body)
    assert trailer == gen
    fgen, fdig = _read_fence()
    assert fgen == gen
    assert fdig == data["index_hex"]
    saved_carry = CARRY.read_text().strip()
    assert saved_carry == data["carry_hex"]
    assert data["span_tag"] == _span_tag(data["unit_digest"], data["carry_hex"], data["gen_epoch"])
    REPORT.unlink()
    _yseal()
    again = json.loads(REPORT.read_text())
    assert again == data


def test_torn_record_uses_live_not_decoy():
    """A torn journal reseals from live units and refreshes fence to the live index_hex."""
    _poison_cache_newer()
    data0 = _rerun_chain()
    FENCE.write_text("gen=1 digest=deadbeefdeadbeef\n")
    raw = JOURNAL.read_bytes()
    JOURNAL.write_bytes(raw[:-8] + b"\x00" * 8)
    REPORT.unlink(missing_ok=True)
    _yseal()
    data = json.loads(REPORT.read_text())
    idx, _ = _index_hex(gen=data["gen_epoch"])
    assert data["index_hex"] == idx
    assert data["unit_digest"] == _unit_digest(data["gen_epoch"], UNITS, idx)
    assert data["unit_digest"] != _unit_digest(data["gen_epoch"], CACHE)
    assert data["gen_epoch"] == data0["gen_epoch"]
    live_probe = _probe_from(UNITS)
    cache_probe = _probe_from(CACHE)
    delta_live = abs(data["probe_sum"] - live_probe)
    delta_cache = abs(data["probe_sum"] - cache_probe)
    assert delta_live <= TOL
    assert delta_cache > 1.0
    fgen, fdig = _read_fence()
    assert fgen == data["gen_epoch"]
    assert fdig == data["index_hex"]
    assert data["span_tag"] == _span_tag(data["unit_digest"], data["carry_hex"], data["gen_epoch"])


def test_multi_run_lineage_budget_edit_torn_cache():
    """Emit, payload edit, budget bump, cache poison, and torn recovery keep coupled lineage."""
    STAMP.write_text("3\n")
    first = _rerun_chain()
    p = UNITS / "u0.bin"
    old = p.read_bytes()
    old_budget = BUDGET.read_text()
    try:
        changed = bytearray(old)
        changed[-1] ^= 0x11
        p.write_bytes(bytes(changed))
        second = _chain_keep_journal()
        assert second["carry_hex"] == first["wal_crc"]
        assert second["index_hex"] != first["index_hex"]
        idx2, _ = _index_hex(gen=second["gen_epoch"])
        assert second["unit_digest"] == _unit_digest(second["gen_epoch"], index=idx2)
        assert second["span_tag"] == _span_tag(
            second["unit_digest"], second["carry_hex"], second["gen_epoch"]
        )
        bumped = second["gen_epoch"] + 5
        BUDGET.write_text(f"gen_epoch = {bumped}\n")
        third = _chain_keep_journal()
        assert third["gen_epoch"] == bumped
        assert third["carry_hex"] == "00000000"
        idx3, _ = _index_hex(gen=bumped)
        assert third["index_hex"] == idx3
        assert third["unit_digest"] == _unit_digest(bumped, index=idx3)
        _poison_cache_newer()
        raw = JOURNAL.read_bytes()
        JOURNAL.write_bytes(raw[:-8] + b"\x00" * 8)
        FENCE.write_text("gen=0 digest=feedfacefeedface\n")
        REPORT.unlink(missing_ok=True)
        _yseal()
        fourth = json.loads(REPORT.read_text())
        assert fourth["unit_digest"] == _unit_digest(bumped, UNITS, idx3)
        assert fourth["unit_digest"] != _unit_digest(bumped, CACHE)
        fgen, fdig = _read_fence()
        assert fgen == bumped
        assert fdig == fourth["index_hex"]
        assert fourth["span_tag"] == _span_tag(
            fourth["unit_digest"], fourth["carry_hex"], fourth["gen_epoch"]
        )
    finally:
        p.write_bytes(old)
        BUDGET.write_text(old_budget)
        STAMP.write_text("3\n")
        _rerun_chain()


def test_report_field_types():
    """The transcript exposes the documented fields with stable types."""
    data = _rerun_chain()
    assert set(data) == {
        "pair_ref",
        "gen_epoch",
        "mesh_id",
        "unit_digest",
        "seal_class",
        "wal_crc",
        "unit_count",
        "probe_sum",
        "stamp_epoch",
        "carry_hex",
        "span_tag",
        "index_hex",
    }
    assert isinstance(data["pair_ref"], str)
    assert isinstance(data["gen_epoch"], int)
    assert isinstance(data["mesh_id"], str) and len(data["mesh_id"]) == 16
    assert isinstance(data["unit_digest"], str) and len(data["unit_digest"]) == 16
    assert data["seal_class"] in {"mesh_hold_t", "mesh_open_t"}
    assert isinstance(data["wal_crc"], str) and len(data["wal_crc"]) == 8
    assert isinstance(data["unit_count"], int) and data["unit_count"] == len(_names())
    assert isinstance(data["probe_sum"], float)
    assert isinstance(data["stamp_epoch"], int)
    assert isinstance(data["carry_hex"], str) and len(data["carry_hex"]) == 8
    assert isinstance(data["span_tag"], str) and len(data["span_tag"]) == 8
    assert isinstance(data["index_hex"], str) and len(data["index_hex"]) == 16


def test_link_graph_no_crc_probe():
    """crc_probe must not appear on packing or seal target link lines in cmake maps."""
    seen = set()
    for path in FORBIDDEN_LINK_TARGETS.values():
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        hits = _crc_probe_link_hits(path.read_text())
        assert hits == [], f"{path} still links crc_probe: {hits}"
    toolchain = ENV / "mk" / "host.cmake"
    text = toolchain.read_text()
    assert "XP_SIDE" not in text
    assert "XP_OPEN" not in text
    assert "XP_PAD" not in text


def test_object_archive_link_graph_provenance():
    """With a clean link graph, digests and mesh ids follow live unit provenance."""
    _poison_cache_newer()
    data = _rerun_chain()
    idx, _ = _index_hex(gen=data["gen_epoch"])
    assert data["index_hex"] == idx
    assert data["unit_digest"] == _unit_digest(data["gen_epoch"], index=idx)
    assert data["mesh_id"] == _bind_hex(data["unit_digest"], "h0")
    live = _unit_digest(data["gen_epoch"], index=idx)
    nib = int(live[-1], 16)
    expect = (
        "mesh_open_t"
        if (nib % 2 == 1 and data["gen_epoch"] == data["stamp_epoch"])
        else "mesh_hold_t"
    )
    assert data["seal_class"] == expect
    assert data["unit_digest"] != _unit_digest(data["gen_epoch"], CACHE)
    assert data["span_tag"] == _span_tag(data["unit_digest"], data["carry_hex"], data["gen_epoch"])
    seen = set()
    for path in FORBIDDEN_LINK_TARGETS.values():
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        assert _crc_probe_link_hits(path.read_text()) == []
    toolchain = ENV / "mk" / "host.cmake"
    text = toolchain.read_text()
    assert "XP_SIDE" not in text
    assert "XP_OPEN" not in text
    assert "XP_PAD" not in text
