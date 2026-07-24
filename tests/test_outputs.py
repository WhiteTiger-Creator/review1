"""Domain checks over regenerated observations and rights sheet artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from itertools import pairwise
from pathlib import Path

ENV = Path("/app/environment")
OUT = Path("/app/output")
JOURNAL = ENV / "var" / "journal"
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


def _load_packs(sub: str) -> list[dict]:
    root = ENV / "corp" / sub
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


def test_v_cold_root_bands():
    """Primary observation bands stay within tol_n of the published fold."""
    _ensure_outputs()
    got = _load_json(OUT / "obs_primary.json")
    exp = _expected_root("primary")
    assert got["root"] == "primary"
    assert len(got["rows"]) == len(exp["rows"])
    by_sid = {r["sid"]: r for r in got["rows"]}
    for er in exp["rows"]:
        gr = by_sid[er["sid"]]
        assert len(gr["bands"]) == len(er["bands"])
        for a, b in zip(gr["bands"], er["bands"]):
            assert _close(a, b), f"band mismatch {er['sid']}"
    assert got["band_digest"] == exp["band_digest"]


def test_v_ladder_transition_cold():
    """Class transitions must not leave stale early bands in the fold."""
    _ensure_outputs()
    got = _load_json(OUT / "obs_primary.json")
    exp = _expected_root("primary")
    by_sid = {r["sid"]: r for r in got["rows"]}
    transitioned = False
    for er in exp["rows"]:
        ladder = er["cls"]
        for left, right in pairwise(ladder):
            if left != right:
                transitioned = True
                break
        gr = by_sid[er["sid"]]
        for a, b in zip(gr["bands"], er["bands"]):
            assert _close(a, b)
        assert gr["cls"] == er["cls"]
    assert transitioned, "fixture must include at least one ladder transition"


def test_v_stable_pair_bands():
    """Stable high-SNR primary packs keep band arithmetic within epsilon."""
    _ensure_outputs()
    got = _load_json(OUT / "obs_primary.json")
    exp = _expected_root("primary")
    by_sid = {r["sid"]: r for r in got["rows"]}
    for sid in ("c0", "c1"):
        assert sid in by_sid
        exp_bands = {r["sid"]: r for r in exp["rows"]}[sid]["bands"]
        for a, b in zip(by_sid[sid]["bands"], exp_bands):
            assert _close(a, b)


def test_v_campaign_budget_vectors():
    """Hold packs recompute fatigue budgets from current bands, not prior zeros."""
    _ensure_outputs()
    got = _load_json(OUT / "obs_hold.json")
    exp = _expected_root("hold")
    by_sid = {r["sid"]: r for r in got["rows"]}
    nonzero = False
    for er in exp["rows"]:
        gr = by_sid[er["sid"]]
        assert len(gr["q"]) == len(er["q"])
        for a, b in zip(gr["q"], er["q"]):
            assert _close(a, b), f"budget mismatch {er['sid']}"
        if any(abs(v) > EPS for v in er["q"]):
            nonzero = True
    assert nonzero
    assert got["q_digest"] == exp["q_digest"]


def test_v_sheet_digest_bind():
    """Rights sheet carries required schema sections bound to budget digests."""
    _ensure_outputs()
    sheet = _load_json(OUT / "rights_map.json")
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    assert sheet["version"] == "k4-1"
    assert "grants" in sheet and isinstance(sheet["grants"], list)
    assert "digests" in sheet and "qdig" in sheet
    assert sheet["qdig"]["primary"] == prim["q_digest"]
    assert sheet["qdig"]["hold"] == hold["q_digest"]
    assert isinstance(sheet.get("neg"), list)
    assert "fld_any" in sheet


def test_v_overwrite_artifacts():
    """Driver overwrites stale /app/output artifacts on rerun."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    stale = OUT / "rights_map.json"
    stale.write_text('{"version":"stale"}\n')
    marker = OUT / "obs_primary.json"
    marker.write_text('{"root":"stale"}\n')
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    sheet = _load_json(stale)
    assert sheet.get("version") == "k4-1"
    prim = _load_json(marker)
    assert prim.get("root") == "primary"


def test_v_campaign_budget_tail():
    """Budget path: hold q vectors must match published fatigue algebra."""
    _ensure_outputs()
    got = _load_json(OUT / "obs_hold.json")
    exp = _expected_root("hold")
    by_sid = {r["sid"]: r for r in got["rows"]}
    for er in exp["rows"]:
        gr = by_sid[er["sid"]]
        assert all(_close(a, b) for a, b in zip(gr["q"], er["q"]))
        if len(er["q"]) > 2:
            tail_got = gr["q"][len(gr["q"]) - 1]
            tail_exp = er["q"][len(er["q"]) - 1]
            if abs(tail_exp) > EPS:
                assert abs(tail_got) > EPS


def test_v_neg_transparency_align():
    """Held-out degradation classes keep non-goals aligned with regenerated digests."""
    _ensure_outputs()
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    text = (OUT / "transparency.txt").read_text()
    s: set[int] = set()
    for r in hold["rows"]:
        for c in r["cls"]:
            if c >= 2:
                s.add(c)
    for r in _load_json(OUT / "obs_primary.json")["rows"]:
        for c in r["cls"]:
            if c >= 2:
                s.add(c)
    expect = [f"ng:{k}" for k in sorted(s)]
    assert sheet["neg"] == expect
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines == expect
    assert sheet["digests"]["hold"] == hold["band_digest"]


def test_v_grant_from_ladder_max():
    """Emit grants match per-sid ladder maxima from regenerated observations."""
    _ensure_outputs()
    prim = _load_json(OUT / "obs_primary.json")
    hold = _load_json(OUT / "obs_hold.json")
    sheet = _load_json(OUT / "rights_map.json")
    rows = {r["sid"]: r for r in prim["rows"] + hold["rows"]}
    grants = {g["sid"]: g["acc"] for g in sheet["grants"]}
    for sid, row in rows.items():
        mx = max(row["cls"]) if row["cls"] else 0
        want = "full" if mx < 2 else "limited"
        assert grants[sid] == want
    assert sheet["digests"]["primary"] == prim["band_digest"]


def test_v_repeat_byte_identity():
    """Repeated driver runs are byte-identical under fixed corpora."""
    names = [
        "obs_primary.json",
        "obs_hold.json",
        "rights_map.json",
        "transparency.txt",
    ]
    proc1 = _run_driver()
    assert proc1.returncode == 0, proc1.stderr
    snap = {name: (OUT / name).read_bytes() for name in names}
    proc2 = _run_driver()
    assert proc2.returncode == 0, proc2.stderr
    for name, data in snap.items():
        assert (OUT / name).read_bytes() == data


def test_v_transition_band_divergence():
    """Premature early-epoch band reuse fails once full trajectory fold is required."""
    _ensure_outputs()
    got = _load_json(OUT / "obs_primary.json")
    exp = _expected_root("primary")
    by_sid = {r["sid"]: r for r in got["rows"]}
    checked = False
    for er in exp["rows"]:
        if len(set(er["cls"])) < 2:
            continue
        gr = by_sid[er["sid"]]
        ladder = er["cls"]
        for idx, (earlier, later) in enumerate(pairwise(ladder), start=1):
            if earlier == later:
                continue
            assert _close(gr["bands"][idx], er["bands"][idx])
            earlier_band = er["bands"][:idx][-1]
            differs = False
            for j in range(idx, len(gr["bands"])):
                if not _close(gr["bands"][j], earlier_band):
                    differs = True
                    break
            assert differs
            checked = True
            break
    assert checked


def test_v_driver_argv_contract():
    """drive_k4 argv contract and exit behavior match public notes."""
    help_proc = _run_driver(["--help"])
    assert help_proc.returncode == 0
    good = _run_driver(["--root", str(ENV), "--out", str(OUT)])
    assert good.returncode == 0, good.stderr
    assert (OUT / "rights_map.json").exists()


def test_v_poisoned_band_seed():
    """Poisoned journal bands must not survive class-transition invalidation."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    exp = _expected_root("hold")
    target = None
    for er in exp["rows"]:
        if len(set(er["cls"])) >= 2:
            target = er
            break
    assert target is not None
    path = JOURNAL / f"{target['sid']}.json"
    assert path.exists()
    rec = json.loads(path.read_text())
    assert "bands" in rec and "gen" in rec and "q" in rec
    poisoned = [v + 0.37 for v in rec["bands"]]
    assert any(not _close(a, b) for a, b in zip(poisoned, rec["bands"]))
    rec["bands"] = poisoned
    path.write_text(json.dumps(rec) + "\n")
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    got = _load_json(OUT / "obs_hold.json")
    by_sid = {r["sid"]: r for r in got["rows"]}
    gr = by_sid[target["sid"]]
    assert len(gr["bands"]) == len(target["bands"])
    for a, b in zip(gr["bands"], target["bands"]):
        assert _close(a, b), f"poisoned journal band stuck for {target['sid']}"
    assert got["band_digest"] == exp["band_digest"]
    # journal must be rewritten to cold-fold bands after a successful run
    rec2 = json.loads(path.read_text())
    assert rec2.get("gen") == rec.get("gen")
    for a, b in zip(rec2["bands"], target["bands"]):
        assert _close(a, b)


def test_v_poisoned_q_replay():
    """Poisoned journal q must not be returned on mode>=1 campaign replay."""
    warm = _run_driver()
    assert warm.returncode == 0, warm.stderr
    exp = _expected_root("hold")
    target = exp["rows"][0]
    path = JOURNAL / f"{target['sid']}.json"
    assert path.exists()
    rec = json.loads(path.read_text())
    assert len(rec.get("q", [])) == len(target["q"])
    rec["q"] = [v * 2.0 + 0.11 for v in rec["q"]]
    assert any(not _close(a, b) for a, b in zip(rec["q"], target["q"]))
    path.write_text(json.dumps(rec) + "\n")
    proc = _run_driver()
    assert proc.returncode == 0, proc.stderr
    got = _load_json(OUT / "obs_hold.json")
    by_sid = {r["sid"]: r for r in got["rows"]}
    gr = by_sid[target["sid"]]
    assert len(gr["q"]) == len(target["q"])
    for a, b in zip(gr["q"], target["q"]):
        assert _close(a, b), f"poisoned journal q reused for {target['sid']}"
    assert got["q_digest"] == exp["q_digest"]
    rec2 = json.loads(path.read_text())
    for a, b in zip(rec2["q"], target["q"]):
        assert _close(a, b)


def test_v_stamp_gen_matches_corpus():
    """After a clean run, journal gen fields stay aligned with pack gen values."""
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
            assert isinstance(rec.get("bands"), list)
            assert len(rec["bands"]) == len(ch["tr"])
            assert isinstance(rec.get("cls"), list)
            assert len(rec["cls"]) == len(ch["tr"])
            assert isinstance(rec.get("q"), list)
            assert len(rec["q"]) == len(ch["tr"])
            checked += 1
    assert checked >= 8


def test_v_limited_grant_presence():
    """At least one primary channel gets a limited grant under the ladder max rule."""
    _ensure_outputs()
    prim = _load_json(OUT / "obs_primary.json")
    sheet = _load_json(OUT / "rights_map.json")
    grants = {g["sid"]: g["acc"] for g in sheet["grants"]}
    limited = 0
    for r in prim["rows"]:
        mx = max(r["cls"]) if r["cls"] else 0
        if mx >= 2:
            assert grants[r["sid"]] == "limited"
            limited += 1
        else:
            assert grants[r["sid"]] == "full"
    assert limited >= 1
