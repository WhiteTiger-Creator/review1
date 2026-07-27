"""Held-out evaluation checks: fold, fatigue budgets, grants, and seal lineage."""

from __future__ import annotations

import hashlib
import json
import subprocess
from itertools import pairwise
from pathlib import Path

ENV = Path("/app/environment")
OUT = Path("/app/output")
JOURNAL = ENV / "var" / "journal"
SEAL = Path("/app/var/psr/eval_seal.json")
LEDGER = Path("/app/run/psr_ledger.jsonl")
EPS = 1e-9


def _run_driver(extra: list[str] | None = None) -> subprocess.CompletedProcess:
    if not extra:
        return subprocess.run(
            ["bash", "/app/environment/drive_k4.sh"],
            cwd="/app/environment",
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    if extra == ["--help"]:
        return subprocess.run(
            ["bash", "/app/environment/drive_k4.sh", "--help"],
            cwd="/app/environment",
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    if (
        len(extra) == 4
        and extra[0] == "--root"
        and extra[2] == "--out"
    ):
        return subprocess.run(
            [
                "bash",
                "/app/environment/drive_k4.sh",
                "--root",
                extra[1],
                "--out",
                extra[3],
            ],
            cwd="/app/environment",
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    raise AssertionError(f"unsupported drive_k4 argv: {extra!r}")


def _ensure_outputs() -> None:
    need = [
        OUT / "obs_primary.json",
        OUT / "obs_hold.json",
        OUT / "rights_map.json",
        OUT / "transparency.txt",
    ]
    if not all(p.exists() for p in need):
        proc = _run_driver()
        assert proc.returncode == 0, f"driver failed: {proc.stderr}\n{proc.stdout}"
    for p in need:
        assert p.exists(), f"missing {p}"


def _mean_pref(tr: list[float], e: int) -> float:
    return sum(tr[: e + 1]) / float(e + 1)


def _rnd6(x: float) -> float:
    if x >= 0:
        return float(int(x * 1e6 + 0.5)) / 1e6
    return float(int(x * 1e6 - 0.5)) / 1e6


def _cls_of(s: float, cuts: list[float]) -> int:
    if s >= cuts[0]:
        return 0
    if s >= cuts[1]:
        return 1
    if s >= cuts[2]:
        return 2
    return 3


def _fold_bands(
    tr: list[float], sl: float, cuts: list[float]
) -> tuple[list[float], list[int]]:
    bands: list[float] = []
    cls: list[int] = []
    for e in range(len(tr)):
        raw = _mean_pref(tr, e) - sl * float(e)
        if raw < 0:
            raw = 0.0
        c = _cls_of(raw, cuts)
        b = _rnd6(raw)
        bands.append(b)
        cls.append(c)
    return bands, cls


def _pow97(i: int) -> float:
    r = 1.0
    for _ in range(i):
        r *= 0.97
    return r


def _budget(bands: list[float], cls: list[int]) -> list[float]:
    out = [0.0] * len(bands)
    acc = 0.0
    for i in range(1, len(bands)):
        den = 1.0 + float(max(cls[i], cls[i - 1]))
        cost = abs(bands[i] - bands[i - 1]) / den
        acc += cost * _pow97(i)
        out[i] = acc
    return out


def _fld(bands: list[float], cls: list[int]) -> int:
    for i in range(1, len(bands)):
        den = 1.0 + float(max(cls[i], cls[i - 1]))
        cost = abs(bands[i] - bands[i - 1]) / den
        if cost > 0.15 and max(cls[i], cls[i - 1]) >= 2:
            return 1
    return 0


def _join_digest(sids: list[str], vectors: dict[str, list[float]]) -> str:
    parts = []
    for sid in sorted(sids):
        cells = [f"{v:.6f}" for v in vectors[sid]]
        parts.append(",".join(cells))
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode()).hexdigest()


def _fnv_mix(h: int, byte: int) -> int:
    h ^= byte & 0xFF
    h = (h * 16777619) & 0xFFFFFFFF
    return h


def _eval_fp() -> str:
    h = 2166136261
    files = sorted((ENV / "fixtures").rglob("*.json"))
    for path in files:
        for b in path.read_bytes():
            h = _fnv_mix(h, b)
    return f"{h:08x}"


def _bind_hex(prim_band: str, hold_band: str, prim_q: str, hold_q: str, fp: str, gen: int) -> str:
    h = 2166136261
    for s in (prim_band, hold_band, prim_q, hold_q, fp):
        for ch in s:
            h = _fnv_mix(h, ord(ch))
    for b in int(gen).to_bytes(8, "little"):
        h = _fnv_mix(h, b)
    return f"{h:08x}"


def _run_recover() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "/app/environment/recover_k4.sh"],
        cwd="/app/environment",
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _load_packs(sub: str) -> list[dict]:
    root = ENV / "fixtures" / sub
    out = []
    for p in sorted(root.glob("*.json")):
        out.append(json.loads(p.read_text()))
    return out


def _expected_root(sub: str) -> dict:
    packs = _load_packs(sub)
    rows = []
    band_map: dict[str, list[float]] = {}
    q_map: dict[str, list[float]] = {}
    sids: list[str] = []
    for pack in packs:
        cuts = pack["cuts"]
        for ch in pack["ch"]:
            bands, cls = _fold_bands(ch["tr"], ch["sl"], cuts)
            q = _budget(bands, cls)
            fld = _fld(bands, cls)
            rows.append(
                {
                    "sid": ch["sid"],
                    "bands": bands,
                    "cls": cls,
                    "q": q,
                    "fld": fld,
                }
            )
            band_map[ch["sid"]] = bands
            q_map[ch["sid"]] = q
            sids.append(ch["sid"])
    return {
        "root": sub,
        "rows": rows,
        "band_digest": _join_digest(sids, band_map),
        "q_digest": _join_digest(sids, q_map),
    }


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= EPS


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _assert_root_matches(got: dict, exp: dict, label: str) -> None:
    assert got["root"] == exp["root"], label
    assert len(got["rows"]) == len(exp["rows"]), label
    by_sid = {r["sid"]: r for r in got["rows"]}
    for er in exp["rows"]:
        gr = by_sid[er["sid"]]
        assert gr["fld"] == er["fld"], f"{label} fld {er['sid']}"
        assert gr["cls"] == er["cls"], f"{label} cls {er['sid']}"
        assert len(gr["bands"]) == len(er["bands"]), label
        assert len(gr["q"]) == len(er["q"]), label
        for a, b in zip(gr["bands"], er["bands"]):
            assert _close(a, b), f"{label} band {er['sid']}"
        for a, b in zip(gr["q"], er["q"]):
            assert _close(a, b), f"{label} q {er['sid']}"
    assert got["band_digest"] == exp["band_digest"], label
    assert got["q_digest"] == exp["q_digest"], label


def _expected_neg(prim: dict, hold: dict) -> list[str]:
    s: set[int] = set()
    for root in (prim, hold):
        for r in root["rows"]:
            for c in r["cls"]:
                if c >= 2:
                    s.add(c)
    return [f"ng:{k}" for k in sorted(s)]


def _expected_grants(prim: dict, hold: dict) -> list[dict]:
    rows = {r["sid"]: r for r in prim["rows"] + hold["rows"]}
    out = []
    for sid in sorted(rows):
        mx = max(rows[sid]["cls"]) if rows[sid]["cls"] else 0
        out.append({"sid": sid, "acc": "full" if mx < 2 else "limited"})
    return out


def _mutate_pack(path: Path, mutator) -> str:
    original = path.read_text()
    obj = json.loads(original)
    mutator(obj)
    path.write_text(json.dumps(obj, separators=(",", ":")) + "\n")
    return original


def _restore_pack(path: Path, original: str) -> None:
    path.write_text(original)


def _assert_sheet_bound(sheet: dict, prim: dict, hold: dict) -> None:
    assert sheet["version"] == "k4-1"
    assert sheet["digests"]["primary"] == prim["band_digest"]
    assert sheet["digests"]["hold"] == hold["band_digest"]
    assert sheet["qdig"]["primary"] == prim["q_digest"]
    assert sheet["qdig"]["hold"] == hold["q_digest"]
    assert sheet["neg"] == _expected_neg(prim, hold)
    assert sheet["grants"] == _expected_grants(prim, hold)
    want_fld = 1 if any(r["fld"] == 1 for r in prim["rows"] + hold["rows"]) else 0
    assert sheet["fld_any"] == want_fld
    text = (OUT / "transparency.txt").read_text()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines == sheet["neg"]


def _checkpoint_path() -> Path:
    return Path("/app/var/psr/quality_checkpoint.json")


def _assert_fit_checkpoint() -> None:
    cp = _checkpoint_path()
    assert cp.exists(), "fit-score must write quality_checkpoint.json"
    doc = _load_json(cp)
    assert doc.get("train_split") == "primary"
    assert doc.get("eval_split") == "hold"
    assert doc.get("loss") == "alert_fatigue_q"
    assert doc.get("metric") == "quality_ladder"
    digest = doc.get("checkpoint_digest")
    assert isinstance(digest, str) and len(digest) == 64
    h = hashlib.sha256()
    for path in sorted((ENV / "fixtures" / "primary").glob("*.json")):
        h.update(path.read_bytes())
    assert digest == h.hexdigest()


def _poison_transition_journals(sub: str) -> list[str]:
    """Seed journals with stale constant bands that would stick without full invalidation."""
    exp = _expected_root(sub)
    poisoned = []
    for er in exp["rows"]:
        if len(set(er["cls"])) < 2:
            continue
        path = JOURNAL / f"{er['sid']}.json"
        if not path.exists():
            continue
        rec = json.loads(path.read_text())
        # Keep gen matched; force every band to the pre-transition value.
        edge = next(
            i for i in range(1, len(er["cls"])) if er["cls"][i] != er["cls"][i - 1]
        )
        stale = float(er["bands"][edge - 1])
        rec["bands"] = [stale] * len(er["bands"])
        rec["q"] = [float(v) + 0.41 for v in er["q"]]
        path.write_text(json.dumps(rec) + "\n")
        poisoned.append(er["sid"])
    return poisoned


def test_v_cold_root_bands():
    """Primary and hold folds match published algebra under multi-pack live mutations."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    _assert_fit_checkpoint()
    for sub in ("primary", "hold"):
        got = _load_json(OUT / f"obs_{sub}.json")
        exp = _expected_root(sub)
        _assert_root_matches(got, exp, sub)

    baseline_p = _expected_root("primary")
    baseline_h = _expected_root("hold")
    p_pack = ENV / "fixtures" / "primary" / "p02.json"
    h_pack = ENV / "fixtures" / "hold" / "h02.json"
    p_orig = _mutate_pack(
        p_pack,
        lambda o: (
            o["ch"][0].__setitem__(
                "tr", [float(v) * 0.91 + 0.017 for v in o["ch"][0]["tr"]]
            ),
            o.__setitem__("cuts", [float(x) - 0.015 for x in o["cuts"]]),
        ),
    )
    h_orig = _mutate_pack(
        h_pack,
        lambda o: o["ch"][0].__setitem__(
            "sl", float(o["ch"][0]["sl"]) + 0.008
        ),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        _assert_fit_checkpoint()
        got_p = _load_json(OUT / "obs_primary.json")
        got_h = _load_json(OUT / "obs_hold.json")
        exp_p = _expected_root("primary")
        exp_h = _expected_root("hold")
        _assert_root_matches(got_p, exp_p, "mut-primary")
        _assert_root_matches(got_h, exp_h, "mut-hold")
        assert exp_p["band_digest"] != baseline_p["band_digest"]
        assert exp_h["q_digest"] != baseline_h["q_digest"]
        b0 = next(r for r in got_p["rows"] if r["sid"] == "b0")
        b0_base = next(r for r in baseline_p["rows"] if r["sid"] == "b0")
        assert any(not _close(a, b) for a, b in zip(b0["bands"], b0_base["bands"]))
        # Cross-split sheet must track both mutated digests.
        sheet = _load_json(OUT / "rights_map.json")
        _assert_sheet_bound(sheet, got_p, got_h)
    finally:
        _restore_pack(p_pack, p_orig)
        _restore_pack(h_pack, h_orig)
        _run_driver()


def test_v_ladder_transition_cold():
    """Class transitions discard stale journal seeds on both splits across warm replays."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    transitions = 0
    for sub in ("primary", "hold"):
        got = _load_json(OUT / f"obs_{sub}.json")
        exp = _expected_root(sub)
        by_sid = {r["sid"]: r for r in got["rows"]}
        for er in exp["rows"]:
            gr = by_sid[er["sid"]]
            assert gr["cls"] == er["cls"]
            for a, b in zip(gr["bands"], er["bands"]):
                assert _close(a, b)
            for left, right in pairwise(er["cls"]):
                if left != right:
                    transitions += 1
    assert transitions >= 2, "fixtures must expose multiple ladder transitions"

    poisoned = _poison_transition_journals("primary") + _poison_transition_journals(
        "hold"
    )
    assert len(poisoned) >= 2

    again = _run_driver()
    assert again.returncode == 0, again.stderr
    for sub in ("primary", "hold"):
        _assert_root_matches(
            _load_json(OUT / f"obs_{sub}.json"), _expected_root(sub), f"warm-{sub}"
        )

    # Third pass after rewriting journals again must still equal cold fold.
    _poison_transition_journals("hold")
    third = _run_driver()
    assert third.returncode == 0, third.stderr
    for sub in ("primary", "hold"):
        _assert_root_matches(
            _load_json(OUT / f"obs_{sub}.json"), _expected_root(sub), f"warm3-{sub}"
        )


def test_v_stable_pair_bands():
    """Stable high-SNR pair stays exact; slope and cut mutations recompute bands and budgets."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    got = _load_json(OUT / "obs_primary.json")
    exp = _expected_root("primary")
    by_sid = {r["sid"]: r for r in got["rows"]}
    for sid in ("c0", "c1"):
        assert sid in by_sid
        er = next(r for r in exp["rows"] if r["sid"] == sid)
        for a, b in zip(by_sid[sid]["bands"], er["bands"]):
            assert _close(a, b)
        for a, b in zip(by_sid[sid]["q"], er["q"]):
            assert _close(a, b)
        assert by_sid[sid]["cls"] == er["cls"]

    pack = ENV / "fixtures" / "primary" / "p03.json"
    original = _mutate_pack(
        pack,
        lambda o: (
            o["ch"][0].__setitem__("sl", float(o["ch"][0]["sl"]) + 0.011),
            o["ch"][1].__setitem__("sl", float(o["ch"][1]["sl"]) + 0.007),
            o.__setitem__("cuts", [float(x) - 0.01 for x in o["cuts"]]),
        ),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        got2 = _load_json(OUT / "obs_primary.json")
        exp2 = _expected_root("primary")
        _assert_root_matches(got2, exp2, "slope-mut")
        for sid in ("c0", "c1"):
            before = next(r for r in exp["rows"] if r["sid"] == sid)["bands"]
            after = next(r for r in exp2["rows"] if r["sid"] == sid)["bands"]
            assert any(not _close(a, b) for a, b in zip(before, after))
            qb = next(r for r in exp["rows"] if r["sid"] == sid)["q"]
            qa = next(r for r in exp2["rows"] if r["sid"] == sid)["q"]
            assert any(not _close(a, b) for a, b in zip(qb, qa))
    finally:
        _restore_pack(pack, original)
        _run_driver()


def test_v_campaign_budget_vectors():
    """Hold budgets recompute under adversarial priors, length mismatch, and live cuts."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    exp = _expected_root("hold")
    _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp, "hold-base")

    for er in exp["rows"]:
        path = JOURNAL / f"{er['sid']}.json"
        rec = json.loads(path.read_text())
        # Near-miss prior: close to truth but shifted so copy-through would fail eps.
        rec["q"] = [v * 1.0000001 + 0.0002 for v in er["q"]]
        path.write_text(json.dumps(rec) + "\n")
    short = JOURNAL / f"{exp['rows'][0]['sid']}.json"
    rec = json.loads(short.read_text())
    rec["q"] = rec["q"][: max(1, len(rec["q"]) // 2)]
    short.write_text(json.dumps(rec) + "\n")
    # Also poison primary journals; hold scoring must ignore them.
    for er in _expected_root("primary")["rows"]:
        path = JOURNAL / f"{er['sid']}.json"
        if path.exists():
            rec = json.loads(path.read_text())
            rec["q"] = [9.9] * len(rec.get("q", [0.0]))
            path.write_text(json.dumps(rec) + "\n")

    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp, "hold-poison")

    pack = ENV / "fixtures" / "hold" / "h02.json"
    original = _mutate_pack(
        pack,
        lambda o: o.__setitem__("cuts", [float(x) - 0.02 for x in o["cuts"]]),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        exp2 = _expected_root("hold")
        _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp2, "hold-cuts")
        assert exp2["q_digest"] != exp["q_digest"]
        # Replay once more with warm journals from the mutated pack.
        proc3 = _run_driver()
        assert proc3.returncode == 0, proc3.stderr
        _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp2, "hold-cuts-2")
    finally:
        _restore_pack(pack, original)
        _run_driver()


def test_v_sheet_digest_bind():
    """Rights sheet digests, grants, neg, and fld_any track both roots after dual mutations."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    _assert_sheet_bound(sheet, prim, hold)

    h_pack = ENV / "fixtures" / "hold" / "h03.json"
    p_pack = ENV / "fixtures" / "primary" / "p04.json"
    h_orig = _mutate_pack(
        h_pack,
        lambda o: o["ch"][0].__setitem__(
            "tr", [max(0.0, float(v) - 0.08) for v in o["ch"][0]["tr"]]
        ),
    )
    p_orig = _mutate_pack(
        p_pack,
        lambda o: o["ch"][0].__setitem__(
            "tr", [max(0.0, float(v) * 0.82 + 0.03) for v in o["ch"][0]["tr"]]
        ),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        prim2 = _load_json(OUT / "obs_primary.json")
        hold2 = _load_json(OUT / "obs_hold.json")
        sheet2 = _load_json(OUT / "rights_map.json")
        _assert_sheet_bound(sheet2, prim2, hold2)
        assert sheet2["qdig"]["hold"] == hold2["q_digest"]
        assert sheet2["digests"]["hold"] == hold2["band_digest"]
        assert sheet2["digests"]["primary"] == prim2["band_digest"]
        assert hold2["band_digest"] != hold["band_digest"]
        assert prim2["band_digest"] != prim["band_digest"]
        assert sheet2["gen"] == prim2["gen"] == hold2["gen"]
        assert sheet2["eval_fp"] == prim2["eval_fp"] == hold2["eval_fp"] == _eval_fp()
    finally:
        _restore_pack(h_pack, h_orig)
        _restore_pack(p_pack, p_orig)
        _run_driver()


def test_v_overwrite_artifacts():
    """Driver overwrites all four artifacts plus checkpoint with domain-correct bodies."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    names = [
        "obs_primary.json",
        "obs_hold.json",
        "rights_map.json",
        "transparency.txt",
    ]
    for name in names:
        (OUT / name).write_text(
            json.dumps(
                {
                    "root": "primary",
                    "rows": [],
                    "band_digest": "0" * 64,
                    "q_digest": "1" * 64,
                    "gen": 999,
                    "eval_fp": "deadbeef",
                }
            )
            + "\n"
        )
    _checkpoint_path().write_text(
        json.dumps({"train_split": "hold", "checkpoint_digest": "00" * 32}) + "\n"
    )
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    for name in names:
        body = (OUT / name).read_text()
        assert '"gen": 999' not in body
        assert '"eval_fp": "deadbeef"' not in body
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    _assert_root_matches(prim, _expected_root("primary"), "ow-prim")
    _assert_root_matches(hold, _expected_root("hold"), "ow-hold")
    _assert_sheet_bound(sheet, prim, hold)
    _assert_fit_checkpoint()


def test_v_campaign_budget_tail():
    """Budget vectors stay monotonic and match algebra at head, mid, and tail indices."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    got = _load_json(OUT / "obs_hold.json")
    exp = _expected_root("hold")
    by_sid = {r["sid"]: r for r in got["rows"]}
    for er in exp["rows"]:
        gr = by_sid[er["sid"]]
        assert len(gr["q"]) == len(er["q"])
        assert _close(gr["q"][0], 0.0)
        for i in range(1, len(er["q"])):
            assert gr["q"][i] + EPS >= gr["q"][i - 1]
            assert _close(gr["q"][i], er["q"][i])
        mid = len(er["q"]) // 2
        assert _close(gr["q"][mid], er["q"][mid])
        assert _close(gr["q"][-1], er["q"][-1])
        if abs(er["q"][-1]) > EPS:
            assert abs(gr["q"][-1]) > EPS

    pack = ENV / "fixtures" / "hold" / "h01.json"
    original = _mutate_pack(
        pack,
        lambda o: (
            o["ch"][1].__setitem__("sl", float(o["ch"][1]["sl"]) + 0.009),
            o["ch"][0].__setitem__(
                "tr", [float(v) * 0.94 + 0.01 for v in o["ch"][0]["tr"]]
            ),
        ),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        exp2 = _expected_root("hold")
        got2 = _load_json(OUT / "obs_hold.json")
        _assert_root_matches(got2, exp2, "tail-mut")
        assert exp2["q_digest"] != exp["q_digest"]
        # Poison q then replay under mutated packs.
        for er in exp2["rows"]:
            path = JOURNAL / f"{er['sid']}.json"
            rec = json.loads(path.read_text())
            rec["q"] = [0.0] * len(rec["q"])
            path.write_text(json.dumps(rec) + "\n")
        proc3 = _run_driver()
        assert proc3.returncode == 0, proc3.stderr
        _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp2, "tail-mut-poison")
    finally:
        _restore_pack(pack, original)
        _run_driver()


def test_v_neg_transparency_align():
    """Non-goals and transparency track class>=2 sets across roots and mutated cuts."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    expect = _expected_neg(prim, hold)
    assert expect, "fixtures must expose degraded classes"
    assert sheet["neg"] == expect
    lines = [ln for ln in (OUT / "transparency.txt").read_text().splitlines() if ln.strip()]
    assert lines == expect
    assert sheet["digests"]["hold"] == hold["band_digest"]
    assert sheet["digests"]["primary"] == prim["band_digest"]

    pack = ENV / "fixtures" / "primary" / "p04.json"
    h_pack = ENV / "fixtures" / "hold" / "h03.json"
    original = _mutate_pack(
        pack,
        lambda o: (
            o.__setitem__("cuts", [0.99, 0.97, 0.95]),
            o["ch"][0].__setitem__(
                "tr", [float(v) * 0.55 + 0.02 for v in o["ch"][0]["tr"]]
            ),
        ),
    )
    h_orig = _mutate_pack(
        h_pack,
        lambda o: (
            o.__setitem__("cuts", [0.98, 0.96, 0.94]),
            o["ch"][0].__setitem__(
                "tr", [max(0.0, float(v) * 0.7 + 0.04) for v in o["ch"][0]["tr"]]
            ),
        ),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        prim2 = _load_json(OUT / "obs_primary.json")
        hold2 = _load_json(OUT / "obs_hold.json")
        sheet2 = _load_json(OUT / "rights_map.json")
        expect2 = _expected_neg(prim2, hold2)
        assert sheet2["neg"] == expect2
        lines2 = [
            ln
            for ln in (OUT / "transparency.txt").read_text().splitlines()
            if ln.strip()
        ]
        assert lines2 == expect2
        assert sheet2["digests"]["primary"] != sheet["digests"]["primary"]
        assert expect2 != expect or sheet2["digests"]["hold"] != sheet["digests"]["hold"]
        _assert_sheet_bound(sheet2, prim2, hold2)
    finally:
        _restore_pack(pack, original)
        _restore_pack(h_pack, h_orig)
        _run_driver()


def test_v_grant_from_ladder_max():
    """Grants follow ladder maxima for every sid and update when classes shift."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    want = _expected_grants(prim, hold)
    assert sheet["grants"] == want
    assert [g["sid"] for g in sheet["grants"]] == sorted(g["sid"] for g in want)
    assert any(g["acc"] == "limited" for g in want)
    assert any(g["acc"] == "full" for g in want)
    assert sheet["digests"]["primary"] == prim["band_digest"]
    assert len(sheet["grants"]) == len({r["sid"] for r in prim["rows"] + hold["rows"]})

    pack = ENV / "fixtures" / "primary" / "p01.json"
    original = _mutate_pack(
        pack,
        lambda o: o.__setitem__("cuts", [0.999, 0.998, 0.997]),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        prim2 = _load_json(OUT / "obs_primary.json")
        hold2 = _load_json(OUT / "obs_hold.json")
        sheet2 = _load_json(OUT / "rights_map.json")
        want2 = _expected_grants(prim2, hold2)
        assert sheet2["grants"] == want2
        a0 = next(g for g in want2 if g["sid"] == "a0")
        assert a0["acc"] == "limited"
        a0_row = next(r for r in prim2["rows"] if r["sid"] == "a0")
        assert max(a0_row["cls"]) >= 2
    finally:
        _restore_pack(pack, original)
        _run_driver()


def test_v_repeat_byte_identity():
    """Three successive runs stay byte-identical, including after a journal rewrite cycle."""
    names = [
        "obs_primary.json",
        "obs_hold.json",
        "rights_map.json",
        "transparency.txt",
    ]
    snaps = []
    digests = []
    for _ in range(3):
        proc = _run_driver()
        assert proc.returncode == 0, proc.stderr
        snaps.append({name: (OUT / name).read_bytes() for name in names})
        digests.append(_checkpoint_path().read_bytes())
    for name in names:
        assert snaps[0][name] == snaps[1][name] == snaps[2][name]
    assert digests[0] == digests[1] == digests[2]

    for path in JOURNAL.glob("*.json"):
        rec = json.loads(path.read_text())
        if "bands" in rec:
            rec["bands"] = [v + 0.5 for v in rec["bands"]]
            path.write_text(json.dumps(rec) + "\n")
        if "q" in rec:
            rec["q"] = [v * 2.0 for v in rec["q"]]
            path.write_text(json.dumps(rec) + "\n")
    fix1 = _run_driver()
    assert fix1.returncode == 0, fix1.stderr
    snap_a = {name: (OUT / name).read_bytes() for name in names}
    fix2 = _run_driver()
    assert fix2.returncode == 0, fix2.stderr
    for name in names:
        assert (OUT / name).read_bytes() == snap_a[name]
    assert _checkpoint_path().read_bytes() == digests[0]


def test_v_transition_band_divergence():
    """Transition channels match cold fold at every epoch after adversarial journal seeds."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    poisoned = _poison_transition_journals("primary") + _poison_transition_journals(
        "hold"
    )
    assert len(poisoned) >= 2
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    checked = 0
    for sub in ("primary", "hold"):
        got = _load_json(OUT / f"obs_{sub}.json")
        exp = _expected_root(sub)
        _assert_root_matches(got, exp, f"trans-{sub}")
        by_sid = {r["sid"]: r for r in got["rows"]}
        for er in exp["rows"]:
            if len(set(er["cls"])) < 2:
                continue
            gr = by_sid[er["sid"]]
            for idx, (earlier, later) in enumerate(pairwise(er["cls"]), start=1):
                if earlier == later:
                    continue
                assert _close(gr["bands"][idx], er["bands"][idx])
                earlier_band = er["bands"][idx - 1]
                assert any(
                    not _close(gr["bands"][j], earlier_band)
                    for j in range(idx, len(gr["bands"]))
                )
                for j in range(idx):
                    assert _close(gr["bands"][j], er["bands"][j])
                # Post-edge epochs must not equal the stale constant poison value.
                stale = earlier_band
                assert any(
                    not _close(gr["bands"][j], stale)
                    for j in range(idx, len(gr["bands"]))
                )
                checked += 1
    assert checked >= 2


def test_v_driver_argv_contract():
    """drive_k4 argv: help, unknown flag, and custom --out regenerate full artifacts."""
    before_cp = (
        _checkpoint_path().read_bytes() if _checkpoint_path().exists() else None
    )
    help_proc = _run_driver(["--help"])
    assert help_proc.returncode == 0
    assert "usage" in (help_proc.stdout + help_proc.stderr).lower()
    if before_cp is not None and _checkpoint_path().exists():
        assert _checkpoint_path().read_bytes() == before_cp

    bad = subprocess.run(
        ["bash", "/app/environment/drive_k4.sh", "--nope"],
        cwd="/app/environment",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert bad.returncode == 2

    alt = Path("/tmp/psr_alt_out")
    if alt.exists():
        for p in alt.iterdir():
            p.unlink()
    else:
        alt.mkdir(parents=True, exist_ok=True)
    (alt / "obs_primary.json").write_text('{"root":"hold","rows":[]}\n')
    good = _run_driver(["--root", str(ENV), "--out", str(alt)])
    assert good.returncode == 0, good.stderr
    for name in (
        "obs_primary.json",
        "obs_hold.json",
        "rights_map.json",
        "transparency.txt",
    ):
        assert (alt / name).exists(), name
    prim = _load_json(alt / "obs_primary.json")
    hold = _load_json(alt / "obs_hold.json")
    assert prim["root"] == "primary"
    assert hold["root"] == "hold"
    assert prim["band_digest"] == _expected_root("primary")["band_digest"]
    assert hold["q_digest"] == _expected_root("hold")["q_digest"]
    sheet = _load_json(alt / "rights_map.json")
    assert sheet["version"] == "k4-1"
    assert sheet["digests"]["primary"] == prim["band_digest"]
    assert sheet["digests"]["hold"] == hold["band_digest"]
    assert sheet["qdig"]["primary"] == prim["q_digest"]
    assert sheet["qdig"]["hold"] == hold["q_digest"]
    expect_neg = _expected_neg(prim, hold)
    assert sheet["neg"] == expect_neg
    assert sheet["grants"] == _expected_grants(prim, hold)
    lines = [
        ln for ln in (alt / "transparency.txt").read_text().splitlines() if ln.strip()
    ]
    assert lines == expect_neg
    _assert_fit_checkpoint()


def test_v_poisoned_band_seed():
    """Poisoned journal bands on every transitioning hold channel are discarded."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    exp = _expected_root("hold")
    targets = [er for er in exp["rows"] if len(set(er["cls"])) >= 2]
    assert len(targets) >= 1
    for i, target in enumerate(targets):
        path = JOURNAL / f"{target['sid']}.json"
        rec = json.loads(path.read_text())
        edge = next(
            j
            for j in range(1, len(target["cls"]))
            if target["cls"][j] != target["cls"][j - 1]
        )
        stale = float(target["bands"][edge - 1])
        rec["bands"] = [stale + 0.21 + 0.05 * i] * len(target["bands"])
        path.write_text(json.dumps(rec) + "\n")
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    got = _load_json(OUT / "obs_hold.json")
    _assert_root_matches(got, exp, "poison-bands")
    for target in targets:
        rec2 = json.loads((JOURNAL / f"{target['sid']}.json").read_text())
        for a, b in zip(rec2["bands"], target["bands"]):
            assert _close(a, b)
        want_gen = None
        for pack in _load_packs("hold"):
            for ch in pack["ch"]:
                if ch["sid"] == target["sid"]:
                    want_gen = int(pack.get("gen", 0))
        assert want_gen is not None
        assert rec2.get("gen") == want_gen
    # Primary must remain cold-correct despite hold journal poison.
    _assert_root_matches(
        _load_json(OUT / "obs_primary.json"), _expected_root("primary"), "prim-ok"
    )


def test_v_poisoned_q_replay():
    """Poisoned journal q on all hold channels cannot survive mode>=1 replay."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    exp = _expected_root("hold")
    assert len(exp["rows"]) >= 2
    for er in exp["rows"]:
        path = JOURNAL / f"{er['sid']}.json"
        rec = json.loads(path.read_text())
        # Exact-length adversarial prior equal to cold Q plus tiny drift.
        rec["q"] = [v + (0.0003 if i % 2 else -0.0003) for i, v in enumerate(er["q"])]
        path.write_text(json.dumps(rec) + "\n")
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    got = _load_json(OUT / "obs_hold.json")
    _assert_root_matches(got, exp, "poison-q")
    proc2 = _run_driver()
    assert proc2.returncode == 0, proc2.stderr
    _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp, "poison-q-2")
    for er in exp["rows"]:
        rec2 = json.loads((JOURNAL / f"{er['sid']}.json").read_text())
        for a, b in zip(rec2["q"], er["q"]):
            assert _close(a, b)


def test_v_stamp_gen_matches_corpus():
    """Journal gen tracks pack gen for all channels, including after a pack gen bump."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    packs = _load_packs("hold") + _load_packs("primary")
    checked = 0
    for pack in packs:
        want = int(pack.get("gen", 0))
        for ch in pack["ch"]:
            path = JOURNAL / f"{ch['sid']}.json"
            assert path.exists(), f"missing journal for {ch['sid']}"
            rec = json.loads(path.read_text())
            assert rec.get("gen") == want
            assert len(rec["bands"]) == len(ch["tr"])
            assert len(rec["cls"]) == len(ch["tr"])
            assert len(rec["q"]) == len(ch["tr"])
            checked += 1
    assert checked >= 8

    pack_path = ENV / "fixtures" / "hold" / "h01.json"
    p_path = ENV / "fixtures" / "primary" / "p02.json"
    original = _mutate_pack(
        pack_path, lambda o: o.__setitem__("gen", int(o.get("gen", 0)) + 7)
    )
    p_orig = _mutate_pack(
        p_path, lambda o: o.__setitem__("gen", int(o.get("gen", 0)) + 3)
    )
    try:
        # Leave stale gen-0 journal bodies on disk before the bump evaluate.
        for path in JOURNAL.glob("*.json"):
            rec = json.loads(path.read_text())
            rec["gen"] = 0
            rec["bands"] = [9.9] * len(rec.get("bands", [0.0]))
            path.write_text(json.dumps(rec) + "\n")
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        obj = json.loads(pack_path.read_text())
        want = int(obj["gen"])
        for ch in obj["ch"]:
            rec = json.loads((JOURNAL / f"{ch['sid']}.json").read_text())
            assert rec.get("gen") == want
            assert len(rec["bands"]) == len(ch["tr"])
        exp = _expected_root("hold")
        _assert_root_matches(_load_json(OUT / "obs_hold.json"), exp, "gen-bump")
        _assert_root_matches(
            _load_json(OUT / "obs_primary.json"), _expected_root("primary"), "gen-bump-p"
        )
        _assert_fit_checkpoint()
    finally:
        _restore_pack(pack_path, original)
        _restore_pack(p_path, p_orig)
        _run_driver()


def test_v_limited_grant_presence():
    """Limited and full grants both appear; aggressive cuts force additional limited grants."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    want = _expected_grants(prim, hold)
    assert sheet["grants"] == want
    limited = sum(1 for g in want if g["acc"] == "limited")
    full = sum(1 for g in want if g["acc"] == "full")
    assert limited >= 1
    assert full >= 1

    pack = ENV / "fixtures" / "primary" / "p02.json"
    original = _mutate_pack(
        pack,
        lambda o: o.__setitem__("cuts", [0.999, 0.998, 0.997]),
    )
    try:
        proc2 = _run_driver()
        assert proc2.returncode == 0, proc2.stderr
        prim2 = _load_json(OUT / "obs_primary.json")
        hold2 = _load_json(OUT / "obs_hold.json")
        sheet2 = _load_json(OUT / "rights_map.json")
        want2 = _expected_grants(prim2, hold2)
        assert sheet2["grants"] == want2
        assert sum(1 for g in want2 if g["acc"] == "limited") >= limited
        b0 = next(g for g in want2 if g["sid"] == "b0")
        assert b0["acc"] == "limited"
        _assert_sheet_bound(sheet2, prim2, hold2)
    finally:
        _restore_pack(pack, original)
        _run_driver()


def test_v_seal_commit_lineage():
    """Evaluate leaves a COMMIT seal matching gen, fingerprint, bind hex, and fit checkpoint."""
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    assert SEAL.exists()
    seal = _load_json(SEAL)
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    assert seal.get("stage") == "COMMIT"
    fp = _eval_fp()
    gen = int(seal["gen"])
    assert gen >= 1
    assert seal.get("eval_fp") == fp
    assert seal.get("bind_hex") == _bind_hex(
        prim["band_digest"],
        hold["band_digest"],
        prim["q_digest"],
        hold["q_digest"],
        fp,
        gen,
    )
    assert int(prim["gen"]) == gen
    assert int(hold["gen"]) == gen
    assert int(sheet["gen"]) == gen
    assert prim["eval_fp"] == fp
    assert hold["eval_fp"] == fp
    assert sheet["eval_fp"] == fp
    assert LEDGER.exists()
    lines = [ln for ln in LEDGER.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 8
    for ln in lines:
        rec = json.loads(ln)
        assert int(rec["gen"]) == gen
        assert rec["eval_fp"] == fp
    _assert_fit_checkpoint()
    _assert_sheet_bound(sheet, prim, hold)


def test_v_journal_recover():
    """Recover rebuilds equivalent artifacts from the ledger under a COMMIT seal."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    snap = {
        name: (OUT / name).read_bytes()
        for name in (
            "obs_primary.json",
            "obs_hold.json",
            "rights_map.json",
            "transparency.txt",
        )
    }
    seal_snap = SEAL.read_bytes()
    for name in snap:
        (OUT / name).unlink()
    proc = _run_recover()
    assert proc.returncode == 0, proc.stderr
    for name, data in snap.items():
        assert (OUT / name).read_bytes() == data
    assert SEAL.read_bytes() == seal_snap
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    assert prim["band_digest"] == _expected_root("primary")["band_digest"]
    assert hold["q_digest"] == _expected_root("hold")["q_digest"]
    _assert_sheet_bound(_load_json(OUT / "rights_map.json"), prim, hold)


def test_v_open_seal_refuse():
    """Recover must refuse when the durable seal is left OPEN."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    seal = _load_json(SEAL)
    seal["stage"] = "OPEN"
    SEAL.write_text(json.dumps(seal) + "\n")
    (OUT / "obs_primary.json").unlink()
    proc = _run_recover()
    assert proc.returncode != 0
    assert _load_json(SEAL)["stage"] == "OPEN"
    assert not (OUT / "obs_primary.json").exists()


def test_v_stale_fp_refuse_and_bump():
    """Pack edit bumps gen; recover refuses a fingerprint-mismatched COMMIT seal."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    before = int(_load_json(OUT / "obs_primary.json")["gen"])
    pack = ENV / "fixtures" / "hold" / "h01.json"
    original = pack.read_text()
    try:
        obj = json.loads(original)
        obj["cuts"] = [float(x) + 0.001 for x in obj["cuts"]]
        pack.write_text(json.dumps(obj, separators=(",", ":")) + "\n")
        proc = _run_driver()
        assert proc.returncode == 0, proc.stderr
        after = int(_load_json(OUT / "obs_primary.json")["gen"])
        assert after == before + 1
        seal = _load_json(SEAL)
        assert seal["stage"] == "COMMIT"
        assert seal["eval_fp"] == _eval_fp()
        assert int(seal["gen"]) == after
        _assert_fit_checkpoint()
        _assert_root_matches(
            _load_json(OUT / "obs_hold.json"), _expected_root("hold"), "bump-hold"
        )
        seal["eval_fp"] = "deadbeef"
        SEAL.write_text(json.dumps(seal) + "\n")
        bad = _run_recover()
        assert bad.returncode != 0
    finally:
        pack.write_text(original)
        _run_driver()
