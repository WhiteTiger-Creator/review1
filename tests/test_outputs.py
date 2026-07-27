"""Verifier for gem-shelfwalk lock-journal recovery algebra."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if (crc & 1) else (crc >> 1)
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


def _u16(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 2], "little")


def _u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def _load_simple_yaml(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.load(fh, Loader=yaml.SafeLoader)


def _fnv1a32(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


APP = Path("/app")
ENV = Path(os.environ.get("KW_ROOT", "/app/environment"))
OUT = Path(os.environ.get("KW_OUT", "/app/output"))
KW = ENV / "tools" / "kw_run"
BLOB = ENV / "fixtures" / "ix_blob.bin"
MX = ENV / "docs" / "mx_rows.yaml"
EXTRA = ENV / "data" / "extra_mtx.yaml"
SEED = ENV / "data" / "walk_seed.txt"
OV_DIR = ENV / "fixtures" / "overlays"
DOSSIER = OUT / "dossier.json"
REPLAY = OUT / "replay.jsonl"
RESTART = OUT / "restart.bin"


def _sha256_hex(data: bytes) -> str:
    tool = ENV / "tools" / "hex_dgst"
    return subprocess.check_output([str(tool)], input=data).decode().strip()


def edge_digest(name: str, ver: str) -> str:
    return _sha256_hex(f"edge|{name}|{ver}".encode())[:16]


def closure_digest(seed: str, tags: list[str]) -> str:
    body = "|".join(sorted(tags))
    return _sha256_hex(f"{seed}|0|{body}".encode())


def bind_token(edge: str, overlay_ref: str, reloc_off: int) -> str:
    return _sha256_hex(f"{edge}|{overlay_ref}|{reloc_off}".encode())[:12]


def parse_blob(data: bytes):
    assert data[:4] == b"GIX1"
    ver = _u16(data, 4)
    count = _u16(data, 6)
    rb = _u32(data, 8)
    crc = _u32(data, 12)
    body = data[16:]
    assert _crc32(body) == crc
    rows = []
    for i in range(count):
        off = 16 + i * 32
        nh = _u32(data, off)
        vtag = _u16(data, off + 4)
        pbits = _u16(data, off + 6)
        abs_off = _u32(data, off + 8)
        length = _u16(data, off + 12)
        flags = _u16(data, off + 14)
        etag = _u32(data, off + 16)
        raw = data[abs_off : abs_off + length]
        parts = raw.decode().split("|", 2)
        rows.append((i, nh, vtag, pbits, abs_off, length, flags, etag, parts[0], parts[1], parts[2]))
    return ver, count, rb, crc, rows


def load_overlays():
    out = {}
    for path in sorted(OV_DIR.glob("*.lock.yaml")):
        doc = _load_simple_yaml(path)
        out[doc["name"]] = doc["pins"]
    return out


def mx_by_id():
    return {r["gem_id"]: r for r in _load_simple_yaml(MX)["rows"]}


def extra_doc():
    return _load_simple_yaml(EXTRA)


def expected_order(rows, gate_first=True):
    def key(r):
        cls = r["opt_class"]
        if gate_first:
            gr = 0 if cls == "gate" else 1
        else:
            gr = 0 if cls == "side" else 1
        return (int(r["priority"]), gr, r["gem_id"])

    ordered = sorted(rows, key=key)
    out = []
    for i, row in enumerate(ordered):
        item = dict(row)
        item["act_ord"] = i
        out.append(item)
    return out


def _clean_outputs(*paths: Path) -> None:
    for p in paths:
        if p.exists():
            p.unlink()


def run_kw(*extra_args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["KW_ROOT"] = str(ENV)
    env["KW_OUT"] = str(OUT)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [str(KW), *extra_args],
        check=True,
        cwd=str(APP),
        env=env,
        capture_output=True,
        text=True,
    )


def load_dossier():
    return json.loads(DOSSIER.read_text())


def load_replay():
    lines = [ln for ln in REPLAY.read_text().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _enc_str(s: str) -> bytes:
    b = s.encode()
    return len(b).to_bytes(2, "little") + b


def _parse_restart(data: bytes):
    assert data[:4] == b"GSJR"
    ver = _u16(data, 4)
    assert ver == int("1")
    hdr_crc = _u32(data, 8)
    body = data[12:]
    assert _fnv1a32(body) == hdr_crc
    off = 0
    walk_base = _u32(body, off)
    off += 4
    gate_first = body[off]
    off += 2
    act_done = _u16(body, off)
    off += 2
    n_comp = _u16(body, off)
    off += 2

    def dec_str(o):
        n = _u16(body, o)
        o += 2
        return body[o : o + n].decode(), o + n

    seed, off = dec_str(off)
    index_crc, off = dec_str(off)
    rbase = _u32(body, off)
    off += 4
    rows = []
    for _ in range(n_comp):
        gem_id, off = dec_str(off)
        ver_s, off = dec_str(off)
        edge, off = dec_str(off)
        ov, off = dec_str(off)
        plat, off = dec_str(off)
        side, off = dec_str(off)
        act_ord = _u32(body, off)
        reloc = _u32(body, off + 4)
        poff = _u32(body, off + 8)
        off += 12
        bind, off = dec_str(off)
        rows.append(
            {
                "gem_id": gem_id,
                "ver": ver_s,
                "edge_digest": edge,
                "overlay_ref": ov,
                "platform": plat,
                "opt_side": side,
                "act_ord": act_ord,
                "reloc_off": reloc,
                "poff": poff,
                "bind_token": bind,
            }
        )
    n_pend = _u16(body, off)
    off += 2
    pending = []
    for _ in range(n_pend):
        gid, off = dec_str(off)
        pending.append(gid)
    n_led = _u16(body, off)
    off += 2
    ledger = []
    canon = b""
    for _ in range(n_led):
        op = _u32(body, off)
        seq = _u32(body, off + 4)
        off += 8
        gid, off = dec_str(off)
        ledger.append((op, seq, gid))
        canon += int(op).to_bytes(4, "little") + int(seq).to_bytes(4, "little") + _enc_str(gid)
    stored = _u32(body, off)
    expect = _fnv1a32(canon)
    return (
        {
            "walk_base": walk_base,
            "gate_first": gate_first,
            "act_done": act_done,
            "seed": seed,
            "index_crc": index_crc,
            "rbase": rbase,
            "rows": rows,
            "pending": pending,
            "ledger": ledger,
        },
        stored == expect,
    )


@pytest.fixture(scope="module")
def built():
    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw()
    return load_dossier(), load_replay()


def test_r1_ix_layout(built):
    """Index record count and gem ids match dossier rows."""
    dossier, _ = built
    ver, count, _rb, _crc, rows = parse_blob(BLOB.read_bytes())
    assert count == len(dossier["rows"])
    assert ver == int("1")
    names = {r[8] for r in rows}
    assert names == {r["gem_id"] for r in dossier["rows"]}


def test_r2_ix_bound(built):
    """reloc_off matches payload_offset - reloc_base + walk_base."""
    dossier, _ = built
    _ver, _count, rb, _crc, rows = parse_blob(BLOB.read_bytes())
    by = {r[8]: r for r in rows}
    seed_base = int(extra_doc()["training_walk_base"])
    for row in dossier["rows"]:
        rec = by[row["gem_id"]]
        expect = rec[4] - rb + seed_base
        assert row["reloc_off"] == expect


def test_r3_ix_crc(built):
    """index_crc matches CRC32 of post-header index bytes."""
    dossier, _ = built
    _ver, _count, _rb, crc, _rows = parse_blob(BLOB.read_bytes())
    assert dossier["index_crc"] == f"{crc:08x}"


def test_r4_ix_payload(built):
    """Row versions and platforms match decoded index payloads."""
    dossier, _ = built
    _ver, _count, _rb, _crc, rows = parse_blob(BLOB.read_bytes())
    by = {r[8]: r for r in rows}
    for row in dossier["rows"]:
        rec = by[row["gem_id"]]
        assert row["ver"] == rec[9]
        assert row["platform"] == rec[10]


def test_r5_fl_digest(built):
    """edge_digest follows the public sha256 edge formula."""
    dossier, _ = built
    for row in dossier["rows"]:
        assert row["edge_digest"] == edge_digest(row["gem_id"], row["ver"])


def test_r6_fl_perm(built):
    """Closure digest is stable under edge-tag permutation."""
    dossier, _ = built
    seed = SEED.read_text().strip()
    tags = [r["edge_digest"] for r in dossier["rows"]]
    assert dossier["closure_digest"] == closure_digest(seed, tags)
    assert dossier["closure_digest"] == closure_digest(seed, list(reversed(tags)))
    assert dossier["closure_digest"] == closure_digest(seed, sorted(tags))


def test_r7_fl_unit(built):
    """Training annex order yields the dossier closure digest."""
    dossier, _ = built
    seed = SEED.read_text().strip()
    extra = extra_doc()
    tags = [
        edge_digest(n, next(r["ver"] for r in dossier["rows"] if r["gem_id"] == n))
        for n in extra["training_annex_order"]
    ]
    assert dossier["closure_digest"] == closure_digest(seed, tags)


def test_r8_or_mx(built):
    """act_ord matches gate-first matrix ordering."""
    dossier, _ = built
    mx = _load_simple_yaml(MX)["rows"]
    ordered = expected_order(mx, gate_first=True)
    got = sorted(dossier["rows"], key=lambda r: r["act_ord"])
    assert [r["gem_id"] for r in got] == [r["gem_id"] for r in ordered]
    for i, row in enumerate(got):
        assert row["act_ord"] == i


def test_r9_or_opt(built):
    """opt_side copies matrix opt_class for each gem."""
    dossier, _ = built
    mx = {r["gem_id"]: r for r in _load_simple_yaml(MX)["rows"]}
    for row in dossier["rows"]:
        assert row["opt_side"] == mx[row["gem_id"]]["opt_class"]


def test_r10_or_tie(built):
    """Priority and gate/side ties match the matrix rules."""
    dossier, _ = built
    mx = mx_by_id()
    ordered = sorted(dossier["rows"], key=lambda r: r["act_ord"])

    def rank(gid: str):
        row = mx[gid]
        return (int(row["priority"]), 0 if row["opt_class"] == "gate" else 1, gid)

    ranks = [rank(r["gem_id"]) for r in ordered]
    assert ranks == sorted(ranks)


def test_r12_em_shape(built):
    """Dossier and transcript expose the required schema fields."""
    dossier, replay = built
    assert dossier["schema"] == "gem-shelf-dossier" + "/" + "v1"
    assert dossier["walk_seed"] == SEED.read_text().strip()
    assert isinstance(dossier["closure_digest"], str) and len(dossier["closure_digest"]) == 64
    assert isinstance(dossier["index_crc"], str) and len(dossier["index_crc"]) == 8
    assert isinstance(dossier["rows"], list) and len(dossier["rows"]) >= 1
    for row in dossier["rows"]:
        for k in (
            "gem_id",
            "edge_digest",
            "platform",
            "overlay_ref",
            "act_ord",
            "opt_side",
            "reloc_off",
            "bind_token",
            "ver",
        ):
            assert k in row
        assert "poff" not in row
    assert isinstance(replay, list) and len(replay) == len(dossier["rows"])


def test_r13_em_bind(built):
    """bind_token matches the public binding formula."""
    dossier, _ = built
    for row in dossier["rows"]:
        assert row["bind_token"] == bind_token(
            row["edge_digest"], row["overlay_ref"], int(row["reloc_off"])
        )


def test_r14_em_twice(built):
    """Second driver run is byte-identical to the first."""
    first = DOSSIER.read_bytes()
    first_r = REPLAY.read_bytes()
    run_kw()
    assert DOSSIER.read_bytes() == first
    assert REPLAY.read_bytes() == first_r


def test_r15_em_crc(built):
    """Emitted index_crc is non-zero and matches the blob CRC."""
    dossier, _ = built
    _ver, _count, _rb, crc, _rows = parse_blob(BLOB.read_bytes())
    assert dossier["index_crc"] == f"{crc:08x}"
    assert int(dossier["index_crc"], 16) != 0


def test_r16_em_zero(built):
    """held_out_violations is zero on the closed algebra."""
    dossier, _ = built
    assert dossier["held_out_violations"] == len([])


def test_r17_ix_held_walk(built):
    """Held-out walk windows must still decode every annex name."""
    _ = built
    _ver, _count, rb, _crc, rows = parse_blob(BLOB.read_bytes())
    extra = extra_doc()
    names = {r[8] for r in rows}
    for sl in extra["slices"]:
        assert set(sl["annex_order"]) == names
        base = int(sl["walk_base"])
        for rec in rows:
            loff = rec[4] - rb + base
            assert isinstance(loff, int)
            raw = BLOB.read_bytes()[rec[4] : rec[4] + rec[5]]
            assert b"|" in raw


def test_r18_ix_reloc_field(built):
    """reloc_off agrees with the reloc rebasing law on training walk."""
    dossier, _ = built
    _ver, _count, rb, _crc, rows = parse_blob(BLOB.read_bytes())
    base = int(extra_doc()["training_walk_base"])
    by = {r[8]: r for r in rows}
    for row in dossier["rows"]:
        rec = by[row["gem_id"]]
        assert row["reloc_off"] == rec[4] - rb + base
        if rb == base:
            assert row["reloc_off"] == rec[4]


def test_r19_fl_held_closure(built):
    """Held-out annex orders keep the same closure digest."""
    dossier, _ = built
    seed = SEED.read_text().strip()
    tags = [r["edge_digest"] for r in dossier["rows"]]
    expect = closure_digest(seed, tags)
    extra = extra_doc()
    for sl in extra["slices"]:
        perm_tags = [
            next(r["edge_digest"] for r in dossier["rows"] if r["gem_id"] == n)
            for n in sl["annex_order"]
        ]
        assert closure_digest(seed, perm_tags) == expect


def test_r20_or_sides_first():
    """--sides-first reverses gate/side ordering on priority ties."""
    _clean_outputs(DOSSIER, REPLAY)
    run_kw("--sides-first")
    dossier = load_dossier()
    mx = _load_simple_yaml(MX)["rows"]
    ordered = expected_order(mx, gate_first=False)
    got = sorted(dossier["rows"], key=lambda r: r["act_ord"])
    assert [r["gem_id"] for r in got] == [r["gem_id"] for r in ordered]
    _clean_outputs(DOSSIER, REPLAY)
    run_kw()


def test_r21_or_priority(built):
    """Activation order is nondecreasing by matrix priority."""
    dossier, _ = built
    mx = {r["gem_id"]: r for r in _load_simple_yaml(MX)["rows"]}
    ordered = sorted(dossier["rows"], key=lambda r: r["act_ord"])
    pris = [int(mx[r["gem_id"]]["priority"]) for r in ordered]
    assert pris == sorted(pris)


def test_r22_em_replay(built):
    """replay.jsonl rows bind 1:1 to dossier rows in act_ord order."""
    dossier, replay = built
    rows = sorted(dossier["rows"], key=lambda r: r["act_ord"])
    assert len(replay) == len(rows)
    for i, (row, ev) in enumerate(zip(rows, replay)):
        assert ev["phase"] == "r" + "ow"
        assert ev["gem_id"] == row["gem_id"]
        assert ev["edge_digest"] == row["edge_digest"]
        assert ev["act_ord"] == row["act_ord"] == i
        assert ev["bind_token"] == row["bind_token"]
        assert ev["overlay_ref"] == row["overlay_ref"]
        assert ev["reloc_off"] == row["reloc_off"]


def test_r23_em_no_static(built):
    """Driver must own the outputs: content stays valid after regeneration."""
    dossier, _ = built
    run_kw()
    d2 = load_dossier()
    assert d2["schema"] == "gem-shelf-dossier" + "/" + "v1"
    assert d2["held_out_violations"] == len([])
    assert d2["closure_digest"] == dossier["closure_digest"]


def test_r24_em_row_cover(built):
    """Every matrix gem appears once with a matching overlay pin."""
    dossier, _ = built
    mx = _load_simple_yaml(MX)["rows"]
    pins = load_overlays()
    ids = [r["gem_id"] for r in dossier["rows"]]
    assert len(ids) == len(set(ids))
    assert set(ids) == {r["gem_id"] for r in mx}
    for row in dossier["rows"]:
        assert pins[row["overlay_ref"]][row["gem_id"]] == row["ver"]


def test_r25_ov_lock_bind(built):
    """overlay_ref values resolve to lock overlay pin maps."""
    dossier, _ = built
    pins = load_overlays()
    for row in dossier["rows"]:
        assert row["overlay_ref"] in pins
        assert row["gem_id"] in pins[row["overlay_ref"]]


def test_r26_seed_echo(built):
    """walk_seed echoes the seeded walk seed file."""
    dossier, _ = built
    assert dossier["walk_seed"] == SEED.read_text().strip()


def test_r27_java_platform(built):
    """Non-ruby matrix platforms and overlays survive into the dossier."""
    dossier, _ = built
    mx = mx_by_id()
    for row in dossier["rows"]:
        assert row["platform"] == mx[row["gem_id"]]["platform"]
        assert row["overlay_ref"] == mx[row["gem_id"]]["overlay_ref"]


def test_r28_hex_case(built):
    """Digest and CRC hex fields are lowercase hexadecimal."""
    dossier, replay = built
    for row in dossier["rows"]:
        assert row["edge_digest"] == row["edge_digest"].lower()
        assert row["bind_token"] == row["bind_token"].lower()
        int(row["edge_digest"], 16)
        int(row["bind_token"], 16)
    assert dossier["closure_digest"] == dossier["closure_digest"].lower()
    assert dossier["index_crc"] == dossier["index_crc"].lower()
    int(dossier["closure_digest"], 16)
    int(dossier["index_crc"], 16)
    for ev in replay:
        assert ev["bind_token"] == ev["bind_token"].lower()
        int(ev["bind_token"], 16)


def test_r29_walk_base_reloc_delta(built):
    """KW_WALK_BASE shifts reloc_off by delta; payloads and identity stay valid."""
    dossier, _ = built
    train_base = int(extra_doc()["training_walk_base"])
    delta = 2048
    probe = train_base + delta
    by_train = {r["gem_id"]: r for r in dossier["rows"]}
    closure = dossier["closure_digest"]
    seed = dossier["walk_seed"]
    crc = dossier["index_crc"]

    _clean_outputs(DOSSIER, REPLAY)
    run_kw(env_extra={"KW_WALK_BASE": str(probe)})
    probed = load_dossier()
    identity_ok = (
        probed["walk_seed"] == seed
        and probed["index_crc"] == crc
        and probed["closure_digest"] == closure
        and probed["held_out_violations"] == len([])
        and {r["gem_id"] for r in probed["rows"]} == set(by_train)
        and all(
            row["ver"] == by_train[row["gem_id"]]["ver"]
            and row["edge_digest"] == by_train[row["gem_id"]]["edge_digest"]
            and row["platform"] == by_train[row["gem_id"]]["platform"]
            and row["overlay_ref"] == by_train[row["gem_id"]]["overlay_ref"]
            and row["act_ord"] == by_train[row["gem_id"]]["act_ord"]
            and row["bind_token"]
            == bind_token(row["edge_digest"], row["overlay_ref"], int(row["reloc_off"]))
            and row["bind_token"] != by_train[row["gem_id"]]["bind_token"]
            for row in probed["rows"]
        )
    )
    assert identity_ok
    reloc_off_pairs = [
        (row["reloc_off"], by_train[row["gem_id"]]["reloc_off"]) for row in probed["rows"]
    ]
    assert all(got == reloc_off + delta for got, reloc_off in reloc_off_pairs)

    _clean_outputs(DOSSIER, REPLAY)
    run_kw()


def test_r30_closure_independent_of_activation(built):
    """Closure digest ignores activation order and depends on sorted edges only."""
    dossier, _ = built
    seed = SEED.read_text().strip()
    tags = [r["edge_digest"] for r in dossier["rows"]]
    by_act = [r["edge_digest"] for r in sorted(dossier["rows"], key=lambda r: r["act_ord"])]
    mx_order = [r["gem_id"] for r in _load_simple_yaml(MX)["rows"]]
    mx_tags = [
        next(r["edge_digest"] for r in dossier["rows"] if r["gem_id"] == g) for g in mx_order
    ]
    expect = closure_digest(seed, tags)
    assert dossier["closure_digest"] == expect and all(
        closure_digest(seed, sample) == expect
        for sample in (by_act, list(reversed(by_act)), mx_tags)
    )


def test_r31_split_agree_full():
    """split_a + split_b agrees with a clean full resolve."""
    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw()
    full_d = DOSSIER.read_bytes()
    full_r = REPLAY.read_bytes()

    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--mode", "split_a", "--cut", "4")
    assert RESTART.exists()
    assert not DOSSIER.exists()

    run_kw("--mode", "split_b")
    assert DOSSIER.read_bytes() == full_d
    assert REPLAY.read_bytes() == full_r


def test_r32_restart_ledger():
    """restart.bin ledger trailer matches the canonical FNV digest."""
    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--mode", "split_a", "--cut", "3")
    st, ledger_digest_matches = _parse_restart(RESTART.read_bytes())
    assert st["act_done"] == sum((1, 1, 1))
    assert len(st["rows"]) == 3
    assert ledger_digest_matches
    assert any(op == 2 for op, _seq, _gid in st["ledger"])  # cut
    # Logical reloc on training base equals absolute poff when rbase == walk_base,
    # but the stored reloc_off must equal poff - rbase + walk_base either way.
    for row in st["rows"]:
        expect = row["poff"] - st["rbase"] + st["walk_base"]
        assert row["reloc_off"] == expect
        assert row["bind_token"] == bind_token(row["edge_digest"], row["overlay_ref"], row["reloc_off"])


def test_r33_resume_walk_base_rebase():
    """split_b under KW_WALK_BASE rebases completed reloc/bind; closure stable."""
    train_base = int(extra_doc()["training_walk_base"])
    delta = 2048
    probe = train_base + delta

    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw(env_extra={"KW_WALK_BASE": str(probe)})
    full = load_dossier()

    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--mode", "split_a", "--cut", "5")
    run_kw("--mode", "split_b", env_extra={"KW_WALK_BASE": str(probe)})
    resumed = load_dossier()

    assert resumed["closure_digest"] == full["closure_digest"]
    assert resumed["held_out_violations"] == len([])
    by_full = {r["gem_id"]: r for r in full["rows"]}
    for row in resumed["rows"]:
        fr = by_full[row["gem_id"]]
        assert row["reloc_off"] == fr["reloc_off"]
        assert row["bind_token"] == fr["bind_token"]
        assert row["act_ord"] == fr["act_ord"]
        assert row["edge_digest"] == fr["edge_digest"]


def test_r34_split_sides_first_agree():
    """sides-first split_a/split_b agrees with sides-first full run."""
    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--sides-first")
    full_d = DOSSIER.read_bytes()
    full_r = REPLAY.read_bytes()

    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--mode", "split_a", "--cut", "4", "--sides-first")
    run_kw("--mode", "split_b", "--sides-first")
    assert DOSSIER.read_bytes() == full_d
    assert REPLAY.read_bytes() == full_r


def test_r35_corrupt_ledger_rejected():
    """Absorb must reject a restart image with a corrupted ledger digest."""
    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--mode", "split_a", "--cut", "4")
    raw = bytearray(RESTART.read_bytes())
    # Flip low byte of trailing u32 ledger digest.
    raw[-1] ^= 0xFF
    RESTART.write_bytes(bytes(raw))
    env = os.environ.copy()
    env["KW_ROOT"] = str(ENV)
    env["KW_OUT"] = str(OUT)
    proc = subprocess.run(
        [str(KW), "--mode", "split_b"],
        cwd=str(APP),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0


def test_r36_resume_cli_overrides_frozen_schedule():
    """split_b CLI gate/side flag reorders pending gems; completed prefix stays."""
    mx = _load_simple_yaml(MX)["rows"]
    gate_ordered = expected_order(mx, gate_first=True)
    prefix = [r["gem_id"] for r in gate_ordered[:4]]
    pending_ids = [r["gem_id"] for r in gate_ordered[4:]]
    pending_mx = [r for r in mx if r["gem_id"] in set(pending_ids)]
    pending_expect = expected_order(pending_mx, gate_first=False)

    _clean_outputs(DOSSIER, REPLAY, RESTART)
    run_kw("--mode", "split_a", "--cut", "4")
    run_kw("--mode", "split_b", "--sides-first")
    dossier = load_dossier()
    got = sorted(dossier["rows"], key=lambda r: r["act_ord"])
    assert [r["gem_id"] for r in got[:4]] == prefix
    assert [r["gem_id"] for r in got[4:]] == [r["gem_id"] for r in pending_expect]
    for i, row in enumerate(got):
        assert row["act_ord"] == i
