"""Verifier for selinux-restorecon-generation labeling station."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path("/app") / "environment"
OUT = Path("/app") / "output"
SCRATCH = ROOT / "scratch"
TRACE = OUT / "reconcile_trace.json"
JOURNAL = SCRATCH / "gen_journal.json"
BOOK = ROOT / "fixtures" / "f1" / "book.json"
PROFILES = ("north", "south")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _path_key(pfx: str) -> str:
    if "(/.*)?" in pfx:
        return pfx.split("(/.*)?", 1)[0]
    return pfx


def _cases() -> list[str]:
    return [
        c.strip()
        for c in (ROOT / "docs" / "d3.txt").read_text(encoding="utf-8").splitlines()
        if c.strip()
    ]


def _load_ranks() -> dict[str, int]:
    ranks: dict[str, int] = {}
    lines = (ROOT / "data" / "e2.tsv").read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        if not line.strip():
            continue
        name, rank = line.split("\t")
        ranks[name] = int(rank)
    return ranks


def _load_boosts(profile: str) -> dict[str, int]:
    boosts: dict[str, int] = {}
    in_boost = False
    for line in (ROOT / "fixtures" / "p1" / f"{profile}.toml").read_text(
        encoding="utf-8"
    ).splitlines():
        raw = line.strip()
        if raw.startswith("[") and raw.endswith("]"):
            in_boost = raw == "[rank_boost]"
            continue
        if not in_boost:
            continue
        if raw.startswith('"') and "=" in raw:
            left, right = raw.split("=", 1)
            boosts[left.strip().strip('"')] = int(right.strip())
    return boosts


def _dropin_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in sorted((ROOT / "fixtures" / "f2").glob("*.fc")):
        mapping: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pfx, typ = line.split("\t", 1)
            mapping[_path_key(pfx)] = typ
        rows[path.name] = mapping
    return rows


def _reference_winners(profile: str) -> list[tuple[str, str, str]]:
    ranks = _load_ranks()
    boosts = _load_boosts(profile)
    rows = _dropin_rows()
    paths = sorted({p for m in rows.values() for p in m})
    winners: list[tuple[str, str, str]] = []
    for path in paths:
        best = None
        for fname, mapping in rows.items():
            if path not in mapping:
                continue
            eff = ranks.get(fname, 0) + boosts.get(fname, 0)
            cand = (eff, fname, mapping[path])
            if best is None or cand[0] > best[0] or (
                cand[0] == best[0] and cand[1] < best[1]
            ):
                best = cand
        assert best is not None
        winners.append((path, best[1], best[2]))
    return winners


def _merged_body(profile: str) -> str:
    winners = _reference_winners(profile)
    return "".join(f"{path}\t{typ}\n" for path, _w, typ in winners)


def _map_fp(case_id: str) -> str:
    paths = json.loads((ROOT / "fixtures" / "f3" / "map.json").read_text(encoding="utf-8"))[
        case_id
    ]
    return _sha256_text("\n".join(paths) + "\n")


def _book() -> dict:
    return json.loads(BOOK.read_text(encoding="utf-8"))


def _reference_bind(case_id: str, profile: str) -> str:
    book = _book()
    merged_sha = _sha256_text(_merged_body(profile))
    pre = f"{int(book['cur'])}|{merged_sha}|{_map_fp(case_id)}|{profile}|{book['tag']}"
    return _sha256_text(pre)


def _reference_seal(runs: list[dict]) -> str:
    ordered = sorted(runs, key=lambda r: (r["case_id"], r["profile"]))
    lines = [f"{r['case_id']}|{r['profile']}|{r['bind_hex']}" for r in ordered]
    return _sha256_text("\n".join(lines) + "\n")


def _assert_healthy_journal(seal: str) -> None:
    assert JOURNAL.is_file()
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    book = _book()
    assert j["poison"] is False
    assert int(j["sealed_cur"]) == int(book["cur"])
    assert j["sealed_tag"] == book["tag"]
    assert j["grid_seal"] == seal


def _wipe_outputs() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    if SCRATCH.exists():
        for child in SCRATCH.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()


def _run_make(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    helper = Path("/tests") / "run_mesh.sh"
    return subprocess.run(
        ["bash", str(helper), *args],
        check=check,
        text=True,
        capture_output=True,
    )


def _regenerate() -> dict:
    _wipe_outputs()
    _run_make("mesh")
    return json.loads(TRACE.read_text(encoding="utf-8"))


def _run_row(trace: dict, case_id: str, profile: str) -> dict:
    for row in trace["runs"]:
        if row["case_id"] == case_id and row["profile"] == profile:
            return row
    raise AssertionError(f"missing run {case_id}/{profile}")


@pytest.fixture()
def fresh_trace() -> dict:
    return _regenerate()


def test_fixture_integrity() -> None:
    """Public fixtures must match baked digests so co-edits cannot fake gold."""
    pins_path = Path("/tests") / "fixture_pins.json"
    pins = json.loads(pins_path.read_text(encoding="utf-8"))
    for rel, digest in pins.items():
        assert _sha256_file(ROOT / rel) == digest


def test_bind_uses_cur_tag_preimage(fresh_trace: dict) -> None:
    """Bind digests follow cur|merged|map|prof|tag across the full grid."""
    for case_id in _cases():
        for profile in PROFILES:
            row = _run_row(fresh_trace, case_id, profile)
            expected = _reference_bind(case_id, profile)
            assert row["bind_hex"] == expected
            bind_path = OUT / "kx" / f"{case_id}_{profile}.bind"
            assert bind_path.read_text(encoding="utf-8").strip() == expected


def test_attribution_rank_boost_and_short_paths(fresh_trace: dict) -> None:
    """Attribution uses short paths plus rank/boost with ascending filename ties."""
    for profile in PROFILES:
        expected = _reference_winners(profile)
        for case_id in _cases():
            row = _run_row(fresh_trace, case_id, profile)
            lines = Path(row["attrib_file"]).read_text(encoding="utf-8").splitlines()
            assert lines[0] == "path\twinner\ttype"
            got = [tuple(line.split("\t")) for line in lines[1:] if line.strip()]
            assert got == [(p, w, t) for p, w, t in expected]
            assert all("(/.*)?" not in p for p, _w, _t in got)


def test_remount_slot_order_prefix_and_epoch(fresh_trace: dict) -> None:
    """Remount entries sort by slot, carry bind prefixes, and stamp book.cur epochs."""
    want_epoch = str(_book()["cur"])
    for case_id in _cases():
        for profile in PROFILES:
            row = _run_row(fresh_trace, case_id, profile)
            remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
            slots = json.loads((ROOT / "fixtures" / "f4" / "slots.json").read_text(
                encoding="utf-8"
            ))[case_id]
            assert len(remount["entries"]) == len(slots)
            slot_names = [e["slot"] for e in remount["entries"]]
            assert slot_names == sorted(slot_names)
            prefix = row["bind_hex"][:16]
            winners = {p: t for p, _w, t in _reference_winners(profile)}
            by_path = {e["path"]: e for e in remount["entries"]}
            for item in slots:
                e = by_path[item["path"]]
                assert e["bind_prefix"] == prefix
                assert len(e["bind_prefix"]) == 16
                assert e["type"] == winners[item["path"]]
                assert e["slot"] == item["slot"]
                assert str(e["gen_epoch"]) == want_epoch


def test_probe_requires_prefix_type_and_epoch(fresh_trace: dict) -> None:
    """Probes require remount presence, type match, 16-hex prefix, and gen_epoch."""
    want_epoch = str(_book()["cur"])
    for case_id in _cases():
        for profile in PROFILES:
            row = _run_row(fresh_trace, case_id, profile)
            assert row["terminal_ok"] is True
            assert row["pulse_ok"] is True
            probe = json.loads(Path(row["probe_file"]).read_text(encoding="utf-8"))
            assert probe["outcomes"]
            assert all(o["ok"] is True for o in probe["outcomes"])
            remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
            prefix = row["bind_hex"][:16]
            assert all(e["bind_prefix"] == prefix for e in remount["entries"])
            assert all(str(e["gen_epoch"]) == want_epoch for e in remount["entries"])


def test_grid_seal_and_healthy_journal(fresh_trace: dict) -> None:
    """grid_seal sorts by case then profile; journal mirrors book and seal."""
    assert fresh_trace["blocked"] is False
    assert fresh_trace["schema_version"] == 1
    expected_runs = []
    for row in fresh_trace["runs"]:
        expected = _reference_bind(row["case_id"], row["profile"])
        assert row["bind_hex"] == expected
        expected_runs.append(
            {
                "case_id": row["case_id"],
                "profile": row["profile"],
                "bind_hex": expected,
            }
        )
    assert fresh_trace["grid_seal"] == _reference_seal(expected_runs)
    assert len(fresh_trace["runs"]) == len(_cases()) * len(PROFILES)
    _assert_healthy_journal(fresh_trace["grid_seal"])


def test_idempotent_republish_keeps_journal(fresh_trace: dict) -> None:
    """Second clean mesh keeps the same seal and healthy journal contents."""
    seal1 = fresh_trace["grid_seal"]
    binds1 = {
        (r["case_id"], r["profile"]): r["bind_hex"] for r in fresh_trace["runs"]
    }
    journal1 = JOURNAL.read_text(encoding="utf-8")
    _run_make("mesh")
    again = json.loads(TRACE.read_text(encoding="utf-8"))
    assert again["grid_seal"] == seal1
    binds2 = {(r["case_id"], r["profile"]): r["bind_hex"] for r in again["runs"]}
    assert binds1 == binds2
    _assert_healthy_journal(seal1)
    j2 = json.loads(JOURNAL.read_text(encoding="utf-8"))
    assert j2 == json.loads(journal1)


def test_flare_blocks_without_recovery() -> None:
    """s2 then s1 without s3 yields blocked zeroed seal."""
    _wipe_outputs()
    _run_make("mesh")
    _run_make("flare")
    _run_make("mesh")
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    assert trace["blocked"] is True
    assert trace["grid_seal"] == "0" * 64
    assert all(r["terminal_ok"] is False for r in trace["runs"])
    assert all(r["bind_hex"] == "0" * 64 for r in trace["runs"])
    assert JOURNAL.is_file()
    assert json.loads(JOURNAL.read_text(encoding="utf-8"))["poison"] is True


def test_skew_marker_alone_blocks() -> None:
    """Either durable poison marker must keep publishes non-terminal."""
    _wipe_outputs()
    _run_make("mesh")
    (SCRATCH / "durable.skew").write_text(
        '{"mode":"skew","marker":"SKEW"}\n', encoding="utf-8"
    )
    _run_make("mesh")
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    assert trace["blocked"] is True
    assert trace["grid_seal"] == "0" * 64


def test_poison_journal_alone_blocks() -> None:
    """A poison generation journal alone must keep publishes non-terminal."""
    _wipe_outputs()
    _run_make("mesh")
    JOURNAL.write_text(
        json.dumps(
            {
                "sealed_cur": 999999,
                "sealed_tag": "POISON",
                "grid_seal": "0" * 64,
                "poison": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for marker in ("durable.bad", "durable.skew"):
        p = SCRATCH / marker
        if p.exists():
            p.unlink()
    _run_make("mesh")
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    assert trace["blocked"] is True
    assert trace["grid_seal"] == "0" * 64


def test_partial_rewind_leaves_blockers() -> None:
    """Clearing only durable.bad must leave skew/journal blockers active."""
    _wipe_outputs()
    _run_make("mesh")
    _run_make("flare")
    (SCRATCH / "durable.bad").unlink(missing_ok=True)
    assert (SCRATCH / "durable.skew").exists()
    assert JOURNAL.is_file()
    _run_make("mesh")
    trace = json.loads(TRACE.read_text(encoding="utf-8"))
    assert trace["blocked"] is True
    assert trace["grid_seal"] == "0" * 64


def test_rewind_clears_markers_journal_and_recovers() -> None:
    """Complete s3 recovery restores a stable terminal seal and healthy journal."""
    _wipe_outputs()
    first = _regenerate()
    seal1 = first["grid_seal"]
    _run_make("flare")
    assert (SCRATCH / "durable.bad").exists()
    assert (SCRATCH / "durable.skew").exists()
    assert JOURNAL.is_file()
    _run_make("mesh")
    poisoned = json.loads(TRACE.read_text(encoding="utf-8"))
    assert poisoned["blocked"] is True
    _run_make("rewind")
    assert not (SCRATCH / "durable.bad").exists()
    assert not (SCRATCH / "durable.skew").exists()
    assert not JOURNAL.exists()
    _run_make("mesh")
    recovered = json.loads(TRACE.read_text(encoding="utf-8"))
    assert recovered["blocked"] is False
    assert recovered["grid_seal"] == seal1
    assert all(r["terminal_ok"] is True for r in recovered["runs"])
    _assert_healthy_journal(seal1)


def test_warm_cache_stale_across_generation_bump() -> None:
    """Warm flags and caches must not freeze remount prefixes or epochs across bumps."""
    _wipe_outputs()
    first = _regenerate()
    case_id = "c01"
    profile = "north"
    row = _run_row(first, case_id, profile)
    old_prefix = row["bind_hex"][:16]
    old_epoch = str(_book()["cur"])
    warm = SCRATCH / "warm" / f"{case_id}_{profile}.flag"
    warm.parent.mkdir(parents=True, exist_ok=True)
    warm.write_text("warm\n", encoding="utf-8")
    cache = OUT / "vz" / f"{case_id}_{profile}.json.cache"
    stale_prefix = "aa" * 8
    cache.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "slot": "s0",
                        "path": "/var/www",
                        "type": "stale",
                        "bind_prefix": stale_prefix,
                        "gen_epoch": old_epoch,
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    original = BOOK.read_text(encoding="utf-8")
    book = json.loads(original)
    book["cur"] = int(book["cur"]) + 9
    book["tag"] = f"u{book['cur']}"
    BOOK.write_text(json.dumps(book, indent=2) + "\n", encoding="utf-8")
    try:
        _run_make("mesh")
        trace = json.loads(TRACE.read_text(encoding="utf-8"))
        row2 = _run_row(trace, case_id, profile)
        expected = _reference_bind(case_id, profile)
        assert row2["bind_hex"] == expected
        remount = json.loads(Path(row2["remount_file"]).read_text(encoding="utf-8"))
        new_prefix = expected[:16]
        new_epoch = str(book["cur"])
        assert new_prefix != old_prefix
        assert all(e["bind_prefix"] == new_prefix for e in remount["entries"])
        assert all(str(e["gen_epoch"]) == new_epoch for e in remount["entries"])
        assert not any(e["bind_prefix"] == stale_prefix for e in remount["entries"])
        assert not warm.exists()
        probe = json.loads(Path(row2["probe_file"]).read_text(encoding="utf-8"))
        assert all(o["ok"] is True for o in probe["outcomes"])
        assert row2["terminal_ok"] is True
        _assert_healthy_journal(trace["grid_seal"])
    finally:
        BOOK.write_text(original, encoding="utf-8")


def test_restart_isolated_outputs_recompute() -> None:
    """Wiping outputs while leaving stale warm/cache must still recompute on republish."""
    _wipe_outputs()
    first = _regenerate()
    seal1 = first["grid_seal"]
    case_id = "c02"
    profile = "south"
    warm = SCRATCH / "warm" / f"{case_id}_{profile}.flag"
    warm.parent.mkdir(parents=True, exist_ok=True)
    warm.write_text("warm\n", encoding="utf-8")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "vz" / f"{case_id}_{profile}.json.cache"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "slot": "z9",
                        "path": "/tmp/lane",
                        "type": "stale",
                        "bind_prefix": "bb" * 8,
                        "gen_epoch": "1",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _run_make("mesh")
    again = json.loads(TRACE.read_text(encoding="utf-8"))
    assert again["grid_seal"] == seal1
    row = _run_row(again, case_id, profile)
    remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
    want_epoch = str(_book()["cur"])
    assert all(str(e["gen_epoch"]) == want_epoch for e in remount["entries"])
    assert all(e["bind_prefix"] == row["bind_hex"][:16] for e in remount["entries"])
    assert row["terminal_ok"] is True
    _assert_healthy_journal(seal1)


def test_mutated_boosts_recompute() -> None:
    """Per-run profile boost mutation changes winners and seals via live recompute."""
    _wipe_outputs()
    south = ROOT / "fixtures" / "p1" / "south.toml"
    original = south.read_text(encoding="utf-8")
    try:
        south.write_text(
            original.replace('"10-core.fc" = 22', '"10-core.fc" = 0').replace(
                '"30-top.fc" = -8', '"30-top.fc" = 40'
            ),
            encoding="utf-8",
        )
        trace = _regenerate()
        winners = {p: w for p, w, _t in _reference_winners("south")}
        assert winners["/opt/svc"] == "30-top.fc"
        row = _run_row(trace, "c05", "south")
        assert row["bind_hex"] == _reference_bind("c05", "south")
        assert row["terminal_ok"] is True
        attrib = Path(row["attrib_file"]).read_text(encoding="utf-8")
        assert "30-top.fc" in attrib
        remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
        assert all(str(e["gen_epoch"]) == str(_book()["cur"]) for e in remount["entries"])
        _assert_healthy_journal(trace["grid_seal"])
    finally:
        south.write_text(original, encoding="utf-8")


def test_hidden_variant_grid() -> None:
    """Hidden case grid under /tests must converge through the same scripts."""
    hidden = Path("/tests") / "hidden_variant"
    cases = (hidden / "d3.txt").read_text(encoding="utf-8")
    maps = (hidden / "map.json").read_text(encoding="utf-8")
    slots = (hidden / "slots.json").read_text(encoding="utf-8")
    d3 = ROOT / "docs" / "d3.txt"
    map_path = ROOT / "fixtures" / "f3" / "map.json"
    slots_path = ROOT / "fixtures" / "f4" / "slots.json"
    bak = (
        d3.read_text(encoding="utf-8"),
        map_path.read_text(encoding="utf-8"),
        slots_path.read_text(encoding="utf-8"),
    )
    try:
        d3.write_text(cases, encoding="utf-8")
        map_path.write_text(maps, encoding="utf-8")
        slots_path.write_text(slots, encoding="utf-8")
        trace = _regenerate()
        assert trace["blocked"] is False
        for row in trace["runs"]:
            assert row["bind_hex"] == _reference_bind(row["case_id"], row["profile"])
            assert row["terminal_ok"] is True
            remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
            assert all(
                str(e["gen_epoch"]) == str(_book()["cur"]) for e in remount["entries"]
            )
        assert trace["grid_seal"] == _reference_seal(
            [
                {
                    "case_id": r["case_id"],
                    "profile": r["profile"],
                    "bind_hex": _reference_bind(r["case_id"], r["profile"]),
                }
                for r in trace["runs"]
            ]
        )
        _assert_healthy_journal(trace["grid_seal"])
    finally:
        d3.write_text(bak[0], encoding="utf-8")
        map_path.write_text(bak[1], encoding="utf-8")
        slots_path.write_text(bak[2], encoding="utf-8")


def test_book_cur_mutation_shifts_bind_and_epoch() -> None:
    """Mutating book.cur/tag forces new digests and remount epochs."""
    original = BOOK.read_text(encoding="utf-8")
    try:
        BOOK.write_text(
            json.dumps({"cur": 41, "prev": 17, "tag": "u41"}, indent=2) + "\n",
            encoding="utf-8",
        )
        trace = _regenerate()
        for case_id in _cases():
            for profile in PROFILES:
                row = _run_row(trace, case_id, profile)
                assert row["bind_hex"] == _reference_bind(case_id, profile)
                remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
                assert all(str(e["gen_epoch"]) == "41" for e in remount["entries"])
                assert row["terminal_ok"] is True
        _assert_healthy_journal(trace["grid_seal"])
    finally:
        BOOK.write_text(original, encoding="utf-8")


def test_coupled_boost_and_book_mutation() -> None:
    """Boost and book mutations in one run must recompute winners, binds, and epochs."""
    south = ROOT / "fixtures" / "p1" / "south.toml"
    south_orig = south.read_text(encoding="utf-8")
    book_orig = BOOK.read_text(encoding="utf-8")
    try:
        south.write_text(
            south_orig.replace('"15-mid.fc" = -5', '"15-mid.fc" = 50'),
            encoding="utf-8",
        )
        BOOK.write_text(
            json.dumps({"cur": 33, "prev": 17, "tag": "u33"}, indent=2) + "\n",
            encoding="utf-8",
        )
        trace = _regenerate()
        winners = {p: w for p, w, _t in _reference_winners("south")}
        assert winners["/var/www"] == "15-mid.fc"
        row = _run_row(trace, "c01", "south")
        assert row["bind_hex"] == _reference_bind("c01", "south")
        remount = json.loads(Path(row["remount_file"]).read_text(encoding="utf-8"))
        assert all(str(e["gen_epoch"]) == "33" for e in remount["entries"])
        assert all(e["bind_prefix"] == row["bind_hex"][:16] for e in remount["entries"])
        assert row["terminal_ok"] is True
        _assert_healthy_journal(trace["grid_seal"])
    finally:
        south.write_text(south_orig, encoding="utf-8")
        BOOK.write_text(book_orig, encoding="utf-8")


def test_north_south_tie_and_negative_boosts(fresh_trace: dict) -> None:
    """North/south boosts diverge; ties and negatives follow effective-rank rules."""
    north = {p: (w, t) for p, w, t in _reference_winners("north")}
    south = {p: (w, t) for p, w, t in _reference_winners("south")}
    assert north != south
    assert north["/var/www"][0] == "15-mid.fc"
    assert south["/var/www"][0] == "10-core.fc"
    assert south["/tmp/lane"][0] == "30-top.fc"
    n_row = _run_row(fresh_trace, "c01", "north")
    s_row = _run_row(fresh_trace, "c01", "south")
    assert n_row["bind_hex"] != s_row["bind_hex"]
    n_attrib = Path(n_row["attrib_file"]).read_text(encoding="utf-8")
    s_attrib = Path(s_row["attrib_file"]).read_text(encoding="utf-8")
    assert "/var/www\t15-mid.fc\t" in n_attrib
    assert "/var/www\t10-core.fc\t" in s_attrib
    s02 = _run_row(fresh_trace, "c02", "south")
    lines = Path(s02["attrib_file"]).read_text(encoding="utf-8").splitlines()
    by_path = {line.split("\t")[0]: line.split("\t")[1] for line in lines[1:] if line}
    assert by_path["/tmp/lane"] == "30-top.fc"
    assert by_path["/var/www"] == "10-core.fc"
