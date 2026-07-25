import hashlib
import json
import math
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path("/app/environment")
PACK = ROOT / "fixtures" / "ax025_pack"
OUT = Path("/app/output/evidence_bundle.tar")
LEDGER_DB = Path("/app/output/shift_ledger.db")
SEED_DB = ROOT / "db" / "shift_ledger_seed.db"
EDGES = [0.00, 0.25, 0.50, 0.75, 1.00]
MARGIN = 0.050000
BUDGET = 8


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_text(text: str) -> str:
    return _sha(text.encode("utf-8"))


def _json_lite_stringify(obj) -> str:
    if obj is None:
        return "null"
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=True)
    if isinstance(obj, (int, float, bool)):
        return json.dumps(obj)
    if isinstance(obj, dict):
        parts = []
        for key, value in obj.items():
            parts.append(f"{_json_lite_stringify(str(key))}:{_json_lite_stringify(value)}")
        return "{" + ",".join(parts) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_json_lite_stringify(x) for x in obj) + "]"
    return json.dumps(str(obj), ensure_ascii=True)


def _manifest_self_hash(cert_hash: str) -> str:
    man_no_self = {"certificate.json": cert_hash}
    return _sha_text(_json_lite_stringify(man_no_self))


def _ledger_rows() -> list[tuple[str, int, str]]:
    out = subprocess.run(
        [
            "sqlite3",
            "-separator",
            "|",
            str(LEDGER_DB),
            "SELECT fingerprint, epoch, marker FROM replay_journal ORDER BY epoch",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        fp, epoch, marker = line.split("|", 2)
        rows.append((fp, int(epoch), marker))
    return rows


def _catalog_files(db_path: Path) -> set[str]:
    out = subprocess.run(
        ["sqlite3", str(db_path), "SELECT pack_file FROM fixture_catalog ORDER BY pack_file"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}


def _load_probes(pack: Path = PACK):
    probes = []
    for path in sorted(pack.glob("*.jsonl")):
        last = 0
        seen = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            epoch = int(row["epoch"])
            if seen and epoch < last:
                raise ValueError(f"non-increasing epoch in {path.name}")
            seen = True
            last = epoch
            probes.append(row)
    return probes


def _fingerprint(pack: Path = PACK) -> str:
    lines = []
    for path in sorted(p for p in pack.rglob("*") if p.is_file()):
        rel = path.relative_to(pack).as_posix()
        lines.append(f"{rel}|{path.stat().st_size}")
    return _sha_text("\n".join(lines))


def _bin_index(x: float) -> int:
    for i in range(4):
        lo, hi = EDGES[i], EDGES[i + 1]
        if i < 3:
            if lo <= x < hi:
                return i
        else:
            if lo <= x <= hi:
                return i
    return 3


def _mi(rows):
    if not rows:
        return 0.0
    joint = [[0, 0] for _ in range(4)]
    b_count = [0, 0, 0, 0]
    u_count = [0, 0]
    for row in rows:
        b = _bin_index(float(row["feats"][0]))
        u = 1 if row["unsafe"] else 0
        joint[b][u] += 1
        b_count[b] += 1
        u_count[u] += 1
    n = float(len(rows))
    mi = 0.0
    for b in range(4):
        for u in range(2):
            c = joint[b][u]
            if c == 0:
                continue
            pbu = c / n
            pb = b_count[b] / n
            pu = u_count[u] / n
            mi += pbu * math.log(pbu / (pb * pu))
    return mi


def _greedy(probes):
    by_id = {}
    for p in probes:
        by_id[p["id"]] = p
    picked = []
    limit = min(BUDGET, len(by_id))
    while len(picked) < limit:
        best = None
        best_mi = -1.0
        for cand, _row in by_id.items():
            if cand in picked:
                continue
            trial = [by_id[i] for i in picked] + [_row]
            mi = _mi(trial)
            if mi > best_mi + 1e-15 or (
                abs(mi - best_mi) <= 1e-15 and (best is None or cand < best)
            ):
                best_mi = mi
                best = cand
        if best is None:
            break
        picked.append(best)
    return picked


def _enclosure(probes, picked_ids):
    by_id = {p["id"]: p for p in probes}
    selected_unsafe = [by_id[i] for i in picked_ids if by_id[i]["unsafe"]]
    if not selected_unsafe:
        return [], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]
    lo = [1.0, 1.0, 1.0]
    hi = [0.0, 0.0, 0.0]
    for p in selected_unsafe:
        for i in range(3):
            lo[i] = min(lo[i], float(p["feats"][i]))
            hi[i] = max(hi[i], float(p["feats"][i]))
    lo = [max(0.0, min(1.0, v - MARGIN)) for v in lo]
    hi = [max(0.0, min(1.0, v + MARGIN)) for v in hi]
    lines = []
    for p in selected_unsafe:
        lines.append(
            f"{p['id']}|{lo[0]:.6f},{lo[1]:.6f},{lo[2]:.6f}|{hi[0]:.6f},{hi[1]:.6f},{hi[2]:.6f}"
        )
    lines.sort()
    return lines, lo, hi


def _inside(vec, lo, hi):
    return all(lo[i] <= float(vec[i]) <= hi[i] for i in range(3))


def _arm_map(probes, lo, hi, picked_ids):
    by_id = {p["id"]: p for p in probes}
    selected_unsafe = [by_id[i] for i in picked_ids if by_id[i]["unsafe"]]
    arms = sorted({p["arm"] for p in probes})
    out = {}
    for arm in arms:
        keep = True
        for p in probes:
            if p["arm"] != arm or not p["unsafe"]:
                continue
            vec = [float(x) for x in p["feats"]]
            if not selected_unsafe or not _inside(vec, lo, hi):
                keep = False
                break
        out[arm] = "KEEP" if keep else "REJECT"
    return out


def _expected():
    probes = _load_probes()
    picked = _greedy(probes)
    enc, lo, hi = _enclosure(probes, picked)
    arms = _arm_map(probes, lo, hi, picked)
    pack_fp = _fingerprint()
    max_epoch = max(int(p["epoch"]) for p in probes)
    by_id = {p["id"]: p for p in probes}
    sel_rows = [{"epoch": int(by_id[i]["epoch"]), "probe_id": i} for i in picked]
    jr_rows = [
        {"epoch": e, "fingerprint": pack_fp, "marker": f"E{e}"}
        for e in range(1, max_epoch + 1)
    ]
    inclusion = _sha_text("\n".join(enc))
    algebra = _sha_text("\n".join(f"{a}|{d}" for a, d in sorted(arms.items())))
    keep = sum(1 for d in arms.values() if d == "KEEP")
    band = round(keep / len(arms), 6) if arms else 0.0
    return picked, sel_rows, jr_rows, inclusion, algebra, band, arms, pack_fp, max_epoch


def _run_gate():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    return subprocess.run(
        [
            "/app/environment/tools/rivet_gate",
            "--pack",
            str(PACK),
            "--db",
            str(LEDGER_DB),
            "--bundle-out",
            str(OUT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _read_bundle():
    assert OUT.is_file(), "missing evidence_bundle.tar"
    with tarfile.open(OUT, "r:") as tf:
        names = set(tf.getnames())
        assert "certificate.json" in names
        assert "manifest.json" in names
        cert_bytes = tf.extractfile("certificate.json").read()
        man_bytes = tf.extractfile("manifest.json").read()
        cert = json.loads(cert_bytes.decode("utf-8"))
        manifest = json.loads(man_bytes.decode("utf-8"))
    return cert, manifest, cert_bytes


@pytest.fixture(scope="module")
def bundle():
    subprocess.run(["/app/environment/scripts/compile_lane.sh"], check=True)
    result = _run_gate()
    assert result.returncode == 0, result.stderr
    return _read_bundle()


def test_rvg_a1(bundle):
    """MI-greedy selection_trace probe_id order matches the closed pack schedule."""
    cert, _, _ = bundle
    picked, *_ = _expected()
    got = [row["probe_id"] for row in cert["selection_trace"]]
    assert got == picked


def test_rvg_a2(bundle):
    """Greedy probe schedule differs from smoke-only ordering when both are available."""
    cert, _, _ = bundle
    picked, *_ = _expected()
    smoke_order = sorted(p["id"] for p in _load_probes() if p["arm"] == "smoke")[:8]
    got = [row["probe_id"] for row in cert["selection_trace"]]
    assert got == picked
    assert len(picked) >= min(BUDGET, len({p["id"] for p in _load_probes()}))
    if smoke_order and picked != smoke_order:
        assert got != smoke_order


def test_rvg_a3(bundle):
    """Shift ledger fixture_catalog rows align with pack assembly files."""
    cert, _, _ = bundle
    assert cert["selection_trace"]
    pack_files = {p.name for p in PACK.glob("*.jsonl")}
    assert _catalog_files(SEED_DB) == pack_files
    assert _catalog_files(LEDGER_DB) == pack_files


def test_rvg_b1(bundle):
    """selection_trace and replay_journal match epoch and fingerprint contract rows."""
    cert, _, _ = bundle
    _, sel_rows, jr_rows, *_ = _expected()
    assert cert["selection_trace"] == sel_rows
    assert cert["replay_journal"] == jr_rows


def test_rvg_b2(bundle):
    """inclusion_digest matches enclosure bytes and obligation keeps all arms."""
    cert, _, _ = bundle
    _, _, _, inclusion, _, _, arms, _, _ = _expected()
    assert cert["inclusion_digest"] == inclusion
    assert all(d == "KEEP" for d in arms.values())


def test_rvg_b3(bundle):
    """algebra_digest matches arm decisions including held-out rot loop context."""
    cert, _, _ = bundle
    _, _, _, _, algebra, _, arms, _, _ = _expected()
    assert cert["algebra_digest"] == algebra
    assert "rot" in arms
    assert all(d == "KEEP" for d in arms.values())


def test_rvg_c1(bundle):
    """Evidence TAR exposes required certificate.json and manifest.json members."""
    cert, manifest, _ = bundle
    for key in (
        "selection_trace",
        "inclusion_digest",
        "algebra_digest",
        "replay_journal",
        "coverage_band",
    ):
        assert key in cert
    assert "certificate.json" in manifest


def test_rvg_c2(bundle):
    """Digests recompute from formulas and manifest cert hash matches bytes."""
    cert, manifest, cert_bytes = bundle
    _, _, _, inclusion, algebra, *_ = _expected()
    assert cert["inclusion_digest"] == inclusion
    assert cert["algebra_digest"] == algebra
    assert manifest["certificate.json"] == _sha(cert_bytes)
    assert manifest["manifest.json"] == _manifest_self_hash(manifest["certificate.json"])


def test_rvg_c3(bundle):
    """coverage_band coherence and foreign fingerprint rejection in shift ledger."""
    cert, _, _ = bundle
    _, _, _, inclusion, algebra, band, _, pack_fp, _ = _expected()
    assert float(cert["coverage_band"]) == band
    assert cert["inclusion_digest"] == inclusion
    assert cert["algebra_digest"] == algebra
    rows = _ledger_rows()
    fps = {fp for fp, _, _ in rows}
    assert "FOREIGN_PACK_ZZ" not in fps
    assert fps == {pack_fp}
