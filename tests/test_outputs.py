"""Runtime checks for synth transcript and independent-replay certificate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ENV = Path(os.environ.get("DRVX_ENV", "/app/environment"))
OUT = Path(os.environ.get("DRVX_OUT", "/app/output"))
BIN = Path(os.environ.get("DRVX_BIN", str(ENV / "tools" / "drvx")))
TRANSCRIPT = OUT / "protocol_transcript.json"
CERT = OUT / "replay_certificate.json"
ANNEX = ENV / "corpus" / "annex29.wav"
SCRATCH = OUT / "scratch"
LATCH = OUT / ".nubx_latch"
SHADOW = OUT / ".nubx_shadow"
RIBX = json.loads((ENV / "corpus" / "ribx.json").read_text(encoding="utf-8"))
META = json.loads((ENV / "data" / "suite_meta.json").read_text(encoding="utf-8"))
SEAL_B = json.loads((ENV / "corpus" / "seal" / "alg_b.json").read_text(encoding="utf-8"))

DENY = {"__proto__", "constructor", "prototype"}

_DIGEST_NS: dict = {}
exec((ENV / "tools" / "digest_ref.py").read_text(encoding="utf-8"), _DIGEST_NS)
sha256_hex = _DIGEST_NS["sha256_hex"]


def _canon(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"))


def _hex(o) -> str:
    return sha256_hex(_canon(o).encode())


def _merge(root, patch, actors):
    allowed = {int(a) for a in actors}

    def clone(v):
        if isinstance(v, dict):
            return {k: clone(x) for k, x in v.items()}
        if isinstance(v, list):
            return [clone(x) for x in v]
        return v

    out = clone(root) if root else {}

    def walk(dst, src):
        for k, v in src.items():
            if k in DENY:
                continue
            if k == "mask":
                m = int(v)
                if any((m & (1 << bit)) and bit not in allowed for bit in range(32)):
                    continue
                dst[k] = m
                continue
            if isinstance(v, dict):
                base = dst.get(k)
                if not isinstance(base, dict):
                    base = {}
                else:
                    base = clone(base)
                dst[k] = base
                walk(base, v)
            elif isinstance(v, list):
                dst[k] = clone(v)
            else:
                dst[k] = v

    walk(out, patch or {})
    return out


def _rev_keys(obj):
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k in sorted(obj.keys(), reverse=True):
        v = obj[k]
        out[k] = _rev_keys(v) if isinstance(v, dict) else v
    return out


def _parse_nubx(annex_bytes: bytes) -> dict:
    by_lane = {}
    i = 0
    n = len(annex_bytes)
    while i + 14 <= n:
        if annex_bytes[i : i + 4] != b"NUBX":
            i += 1
            continue
        lane_len = annex_bytes[i + 4]
        if i + 5 + lane_len + 9 > n:
            i += 1
            continue
        lane = annex_bytes[i + 5 : i + 5 + lane_len].decode("utf-8")
        base = i + 5 + lane_len
        t0 = int.from_bytes(annex_bytes[base : base + 4], "big")
        t1 = int.from_bytes(annex_bytes[base + 4 : base + 8], "big")
        tx_len = annex_bytes[base + 8]
        if base + 9 + tx_len > n:
            i += 1
            continue
        tx = annex_bytes[base + 9 : base + 9 + tx_len].decode("utf-8")
        by_lane.setdefault(lane, []).append({"t0": t0, "t1": t1, "tx": tx})
        i = base + 9 + tx_len
    for rows in by_lane.values():
        rows.sort(key=lambda w: (w["t0"], w["t1"], w["tx"]))
    return by_lane


def _grant(windows, deltas, ribx):
    wins = sorted(list(windows), key=lambda w: (w["t0"], w["t1"], w["tx"]))
    dels = list(deltas)
    gm = int(ribx["grant_mask"])
    acc = 0
    esc = 0
    n = max(len(wins), len(dels))
    for i in range(n):
        d = dels[i] if i < len(dels) else 0
        if d & ~gm:
            esc += 1
            continue
        acc = (acc + (d & gm)) & 0xFFFFFFFF
    slots = ribx["slots"]
    band = acc & 0xFF
    matched = False
    for s in slots:
        if acc >= s["lo"] and acc < s["hi"]:
            band = s["mid"]
            matched = True
            break
    if not matched and slots:
        band = slots[-1]["mid"]
    payload = {
        "acc": acc,
        "band": band,
        "dels": dels,
        "esc": esc,
        "wins": [[w["t0"], w["t1"], w["tx"]] for w in wins],
    }
    return band, _hex(payload), esc


def _contains_deny(obj) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in DENY:
                return True
            if _contains_deny(v):
                return True
    elif isinstance(obj, list):
        return any(_contains_deny(x) for x in obj)
    return False


def _expected_suite():
    annex = _parse_nubx(ANNEX.read_bytes())
    slabs = []
    for f in sorted((ENV / "corpus" / "slabs").glob("s*.bin")):
        slabs.append(json.loads(f.read_text(encoding="utf-8")))
    rows = []
    for lane in META["lanes"]:
        sl = next(s for s in slabs if s["lane"] == lane)
        folded = _merge(sl["root"], sl["patch"], sl["actors"])
        pair = _merge(sl["root"], _rev_keys(sl["patch"]), sl["actors"])
        windows = annex[lane]
        deltas = list(sl["deltas"])
        while len(deltas) < len(windows):
            deltas.append(0)
        kh, ph = _hex(folded), _hex(pair)
        rows.append(
            {
                "lane": lane,
                "knit_hex": kh,
                "pair_hex": ph,
                "esc_hits": 0,
                "win_count": len(windows),
                "windows": windows,
                "deltas": deltas,
                "folded": folded,
            }
        )
    parts = "|".join(
        f"{r['lane']}:{r['knit_hex']}:{r['pair_hex']}:{r['esc_hits']}" for r in rows
    )
    suite = sha256_hex(parts.encode())
    all_w, all_d = [], []
    for r in rows:
        all_w += r["windows"]
        all_d += r["deltas"]
    band, digest, esc = _grant(all_w, all_d, RIBX)
    return rows, suite, band, digest, esc


def _recompile():
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["go", "build", "-o", str(BIN), "./cmd/drvx"],
        cwd=str(ENV),
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "CGO_ENABLED": "0"},
    )
    bin_dir = Path("/app/bin")
    if bin_dir.exists() or str(BIN).startswith("/app/"):
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BIN, bin_dir / "drvx")


def _plant_decoys(windows_by_lane: dict):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    LATCH.mkdir(parents=True, exist_ok=True)
    SHADOW.mkdir(parents=True, exist_ok=True)
    for lane, wins in windows_by_lane.items():
        bogus = [
            {"t0": 1, "t1": 2, "tx": f"scratch-{lane}-{i}"} for i, _ in enumerate(wins)
        ]
        (SCRATCH / f"lane_{lane}.json").write_text(
            json.dumps({"lane": lane, "windows": bogus}),
            encoding="utf-8",
        )
        (LATCH / f"lane_{lane}.json").write_text(
            json.dumps(
                {"lane": lane, "generation": 99, "windows": bogus},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    (SHADOW / "band.json").write_text(
        json.dumps({"band": 1, "digest": "deadbeef", "esc": 0, "note": "hostile"}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _clean_outputs():
    OUT.mkdir(parents=True, exist_ok=True)
    if TRANSCRIPT.exists():
        TRANSCRIPT.unlink()
    if CERT.exists():
        CERT.unlink()


def _synth():
    _recompile()
    exp_rows, _, _, _, _ = _expected_suite()
    windows = {r["lane"]: r["windows"] for r in exp_rows}
    _clean_outputs()
    _plant_decoys(windows)
    subprocess.run(
        [str(BIN), "synth", "--annex", str(ANNEX), "--out", str(TRANSCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "DRVX_ENV": str(ENV), "DRVX_OUT": str(OUT)},
    )
    assert TRANSCRIPT.exists(), "synth did not write protocol_transcript.json"
    return json.loads(TRANSCRIPT.read_text(encoding="utf-8"))


def _certify():
    subprocess.run(
        [
            str(BIN),
            "certify",
            "--transcript",
            str(TRANSCRIPT),
            "--report",
            str(CERT),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "DRVX_ENV": str(ENV), "DRVX_OUT": str(OUT)},
    )
    assert CERT.exists(), "certify did not write replay_certificate.json"
    return json.loads(CERT.read_text(encoding="utf-8"))


def _row_map(doc: dict) -> dict:
    return {row["lane"]: row for row in doc["rows"]}


def test_w01_deep_sentinel_quarantine():
    """Nested pollution sentinels must not survive the folded bag surface."""
    doc = _synth()
    rows = _row_map(doc)
    exp_rows, suite, _, _, _ = _expected_suite()
    assert doc.get("schema") == "nubx-transcript-v1"
    assert doc.get("escalation_total") == 0
    assert doc.get("suite_digest") == suite
    for er in exp_rows:
        lane = er["lane"]
        assert rows[lane]["knit_hex"] == er["knit_hex"]
        assert rows[lane]["pair_hex"] == er["knit_hex"]
        assert rows[lane]["esc_hits"] == 0
        assert not _contains_deny(er["folded"])
        assert "__proto__" not in _canon(er["folded"])
        assert "constructor" not in json.dumps(er["folded"])
        assert "prototype" not in json.dumps(er["folded"])


def test_w02_endian_clock_authority():
    """Both annex sample bounds are big-endian; latch/scratch must not win."""
    doc = _synth()
    rows = _row_map(doc)
    annex = _parse_nubx(ANNEX.read_bytes())
    for lane in META["lanes"]:
        assert rows[lane]["windows"] == annex[lane]
        scratch = json.loads((SCRATCH / f"lane_{lane}.json").read_text(encoding="utf-8"))
        latch = json.loads((LATCH / f"lane_{lane}.json").read_text(encoding="utf-8"))
        assert scratch["windows"] != annex[lane]
        assert latch["windows"] != annex[lane]
        assert latch.get("generation", 0) != 0
        assert rows[lane]["win_count"] == len(annex[lane])
        for w in rows[lane]["windows"]:
            assert isinstance(w["t0"], int) and isinstance(w["t1"], int)


def test_w03_shadow_band_poison():
    """Dashboard shadow caches must not override independent ribx folds."""
    _synth()
    exp_rows, _, band, digest, _ = _expected_suite()
    _plant_decoys({r["lane"]: r["windows"] for r in exp_rows})
    # Strengthen hostile shadow after synth.
    SHADOW.mkdir(parents=True, exist_ok=True)
    (SHADOW / "band.json").write_text(
        json.dumps({"band": 99, "digest": "cafebabe" * 8, "esc": 0}, indent=2) + "\n",
        encoding="utf-8",
    )
    cert = _certify()
    assert cert.get("schema") == "nubx-replay-v1"
    assert cert["digest"] == cert["replay_digest"]
    assert cert["digest"] == digest
    assert cert["band"] == band
    assert cert["band"] != 99
    assert cert["digest"] != "cafebabe" * 8
    assert all(obs.get("replay_match") is True for obs in cert["observations"])
    assert all(obs.get("esc", 0) == 0 for obs in cert["observations"])


def test_w04_delta_order_decouple():
    """Window reordering must not reshuffle delta semantics in the certificate fold."""
    doc = _synth()
    _, _, band, digest, _ = _expected_suite()
    mutated = json.loads(json.dumps(doc))
    for row in mutated["rows"]:
        row["windows"] = list(reversed(row["windows"]))
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(OUT), delete=False, encoding="utf-8"
    ) as tf:
        tf.write(json.dumps(mutated, indent=2) + "\n")
        alt = Path(tf.name)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(OUT), delete=False, encoding="utf-8"
    ) as rf:
        report = Path(rf.name)
    subprocess.run(
        [str(BIN), "certify", "--transcript", str(alt), "--report", str(report)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "DRVX_ENV": str(ENV), "DRVX_OUT": str(OUT)},
    )
    cert = json.loads(report.read_text(encoding="utf-8"))
    assert cert["digest"] == digest
    assert cert["band"] == band
    assert cert["in_band"] is True


def test_w05_heldout_cross_seal():
    """Annex, transcript windows, held-out labels, and certificate band stay aligned."""
    doc = _synth()
    cert = _certify()
    rows = _row_map(doc)
    annex = _parse_nubx(ANNEX.read_bytes())
    _, _, band, digest, _ = _expected_suite()
    for lane in META["lanes"]:
        assert rows[lane]["windows"] == annex[lane]
    for lane, txs in SEAL_B.get("held_out_txs", {}).items():
        assert [w["tx"] for w in rows[lane]["windows"]] == txs
    assert cert["band"] == band
    assert cert["digest"] == digest
    assert cert["in_band"] is True


def test_w06_mask_and_grant_refusal():
    """Reliability band lands in published slots; out-of-mask deltas escalate."""
    _synth()
    cert = _certify()
    _, _, band, digest, _ = _expected_suite()
    slots = RIBX["slots"]
    assert cert["in_band"] is True
    assert cert["band"] == band
    assert any(s["lo"] <= cert["band"] < s["hi"] for s in slots)
    doc = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    doc["rows"][0]["deltas"] = [1, 2, 64]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(OUT), delete=False, encoding="utf-8"
    ) as tf:
        tf.write(json.dumps(doc, indent=2) + "\n")
        poisoned = Path(tf.name)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(OUT), delete=False, encoding="utf-8"
    ) as rf:
        report = Path(rf.name)
    subprocess.run(
        [str(BIN), "certify", "--transcript", str(poisoned), "--report", str(report)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "DRVX_ENV": str(ENV), "DRVX_OUT": str(OUT)},
    )
    poison_cert = json.loads(report.read_text(encoding="utf-8"))
    assert poison_cert["observations"][0]["esc"] >= 1
    assert poison_cert["digest"] != digest


def test_w07_restart_dual_fold():
    """Synth is idempotent; certify must not rewrite transcript; residuals must not drift."""
    first = _synth()
    before = TRANSCRIPT.read_bytes()
    _plant_decoys({r["lane"]: r["windows"] for r in _expected_suite()[0]})
    _certify()
    after = TRANSCRIPT.read_bytes()
    assert before == after
    second = _synth()
    _, suite, _, _, _ = _expected_suite()
    assert first == second
    assert second["suite_digest"] == suite


def test_w08_closed_commute_under_residuals():
    """Closed-algebra multipack covers every lane knit digest under quarantine."""
    doc = _synth()
    rows = _row_map(doc)
    exp_rows, suite, _, _, _ = _expected_suite()
    assert len(rows) == len(exp_rows)
    assert doc["suite_digest"] == suite
    assert doc["escalation_total"] == 0
    for er in exp_rows:
        lane = er["lane"]
        assert rows[lane]["knit_hex"] == er["knit_hex"]
        assert rows[lane]["pair_hex"] == er["knit_hex"]
        assert [w["tx"] for w in rows[lane]["windows"]] == [w["tx"] for w in er["windows"]]
