"""Verifier for nugetfix packages-lock offline task."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path

import pytest
import tomllib

APP = Path("/app")
FIXTURES = Path("/tests/fixtures")
DIST = APP / "dist"
MATRIX = FIXTURES / "config" / "release_matrix.csv"

H_CORE = "sha256:corecorecorecorecorecorecorecorecorecorecorecorecorecorecoreco"
H_UTILS = "sha256:utilsutilsutilsutilsutilsutilsutilsutilsutilsutilsutilsutilsutil"
H_GATE = "sha256:gategategategategategategategategategategategategategategategate"
H_MET = "sha256:metmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetmetm"
PLAT = "nupkg"
GUARD = (
    "fixtures/bad-lock: hash fail-closed\n"
    "expected: packages.lock.json hash mismatch against nuget-cache\n"
    "expected: leave fixtures/bad-lock unrepaired\n"
)
REQUIRED_BUNDLE_FILES = (
    "bin/nugetfix", "LICENSES.txt", "VERSION", "share/lane-policy.json",
    "share/edges.csv", "share/artifacts.csv", "share/packages.csv", "share/xor.csv",
    "share/peers.csv", "share/feedtags.csv", "share/cache-index.csv", "share/pins.csv",
    "share/advisories.csv", "share/bans.csv", "share/run-smoke.sh", "share/audit-preview.json",
)
LANE_FILTERED_SHARES = (
    ("data/graphs/edges.csv", "share/edges.csv", 0),
    ("data/graphs/artifacts.csv", "share/artifacts.csv", 0),
    ("config/packages.csv", "share/packages.csv", 0),
    ("config/xor.csv", "share/xor.csv", 0),
    ("config/peers.csv", "share/peers.csv", 0),
)
COPIED_SHARES = (
    ("config/feedtags.csv", "feedtags.csv"),
    ("nuget-cache/index.csv", "cache-index.csv"),
    ("config/pins.csv", "pins.csv"),
    ("config/advisories.csv", "advisories.csv"),
    ("config/bans.csv", "bans.csv"),
)


@pytest.fixture(scope="session")
def release_dist() -> Path:
    """Build the release package once from the task workspace."""
    run_release()
    return DIST


def run_release() -> None:
    env = os.environ.copy()
    env["CARGO_NET_OFFLINE"] = "true"
    env["SOURCE_DATE_EPOCH"] = "1700000000"
    subprocess.run(["bash", "/app/scripts/release.sh"], cwd=APP, env=env, check=True, timeout=360)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def matrix_rows() -> list[dict[str, str]]:
    with MATRIX.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _filter_csv_text(src: Path, col: int, lane: str) -> str:
    lines = src.read_text(encoding="utf-8").splitlines()
    header = lines[0]
    rows = [ln for ln in lines[1:] if ln and ln.split(",")[col] == lane]
    body = "\n".join(rows)
    return header + "\n" + (body + "\n" if body else "")


def materialize_lane_share(lane: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for src_rel, dest_rel, col in LANE_FILTERED_SHARES:
        (dest / Path(dest_rel).name).write_text(_filter_csv_text(FIXTURES / src_rel, col, lane), encoding="utf-8", newline="\n")
    for src_rel, name in COPIED_SHARES:
        (dest / name).write_text((FIXTURES / src_rel).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


def assert_lane_share_files(bundle: Path, lane: str) -> None:
    for rel in REQUIRED_BUNDLE_FILES:
        assert (bundle / rel).is_file(), f"missing {rel}"
    for src_rel, dest_rel, col in LANE_FILTERED_SHARES:
        assert (bundle / dest_rel).read_text(encoding="utf-8") == _filter_csv_text(FIXTURES / src_rel, col, lane)
    for src_rel, name in COPIED_SHARES:
        assert (bundle / "share" / name).read_text(encoding="utf-8") == (FIXTURES / src_rel).read_text(encoding="utf-8")


def run_packaged_audit(bundle: Path, lane: str, retention_hops: int, share: Path) -> dict:
    binary = bundle / "bin" / "nugetfix"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        out = Path(handle.name)
    try:
        cmd = [str(binary), "audit", "--lane", lane, "--edges", str(share / "edges.csv"),
               "--artifacts", str(share / "artifacts.csv"), "--packages", str(share / "packages.csv"),
               "--cache", str(share / "cache-index.csv"), "--pins", str(share / "pins.csv"),
               "--feedtags", str(share / "feedtags.csv"), "--advisories", str(share / "advisories.csv"),
               "--xor", str(share / "xor.csv"), "--bans", str(share / "bans.csv"),
               "--peers", str(share / "peers.csv"),
               "--retention-hops", str(retention_hops), "--out", str(out)]
        subprocess.run(cmd, check=True, timeout=120)
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        out.unlink(missing_ok=True)


def test_version(release_dist: Path) -> None:
    """Verify packaged nugetfix binary reports version 1.59.0."""
    lane = matrix_rows()[0]["lane"]
    binary = release_dist / "bundles" / f"nugetfix-{lane}" / "bin" / "nugetfix"
    assert subprocess.check_output([str(binary), "--version"], text=True).strip() == "nugetfix 1.59.0"


def test_hash_layout(release_dist: Path) -> None:
    """Verify lock digests, reports, matrix/graphs match fixtures; legacy_cleared re-derives."""
    _ = release_dist
    lock = (APP / "packages.lock.json").read_text(encoding="utf-8")
    for h in [H_CORE, H_UTILS, H_GATE, H_MET]:
        assert h in lock
    for pkg in ("Ledger.Core", "Ledger.Utils", "Ledger.Gateway", "Ledger.Metrics"):
        assert f'"{pkg}"' in lock
    assert '"ledger-core"' not in lock
    assert "BADCORE" not in lock and "win_amd64" not in lock
    assert (APP / "legacy-nuget-notes.txt").read_text(encoding="utf-8").strip() == "# emptied for nuget"
    assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == GUARD
    assert (DIST / "ledger-check.txt").read_text(encoding="utf-8").splitlines() == [
        "restore-ok:ledger-core", "restore-ok:ledger-utils", "restore-ok:ledger-gateway", "restore-ok:ledger-metrics",
    ]
    assert (DIST / "ledger").read_text(encoding="utf-8") == "publish-ready\n"
    report = json.loads((DIST / "nuget-report.json").read_text(encoding="utf-8"))
    assert report == {
        "format_version": 1, "package_count": 4, "offline_ci": True, "legacy_cleared": True,
        "nuget_dir": "/app/nuget-cache", "platform_tag": PLAT,
    }
    assert (APP / "config" / "packages.csv").read_text(encoding="utf-8") == (FIXTURES / "config" / "packages.csv").read_text(encoding="utf-8")
    assert (APP / "nuget-cache" / "index.csv").read_text(encoding="utf-8") == (FIXTURES / "nuget-cache" / "index.csv").read_text(encoding="utf-8")
    assert (APP / "config" / "feedtags.csv").read_text(encoding="utf-8") == (
        FIXTURES / "config" / "feedtags.csv"
    ).read_text(encoding="utf-8")
    assert (APP / "config" / "release_matrix.csv").read_text(encoding="utf-8") == (
        FIXTURES / "config" / "release_matrix.csv"
    ).read_text(encoding="utf-8")
    assert (APP / "data" / "graphs" / "edges.csv").read_text(encoding="utf-8") == (
        FIXTURES / "data" / "graphs" / "edges.csv"
    ).read_text(encoding="utf-8")
    assert (APP / "data" / "graphs" / "artifacts.csv").read_text(encoding="utf-8") == (
        FIXTURES / "data" / "graphs" / "artifacts.csv"
    ).read_text(encoding="utf-8")
    assert (APP / "config" / "peers.csv").read_text(encoding="utf-8") == (
        FIXTURES / "config" / "peers.csv"
    ).read_text(encoding="utf-8")
    notes_path = APP / "legacy-nuget-notes.txt"
    expected_notes = "# emptied for nuget\n"
    notes_path.write_text("legacy notes: still dirty\n", encoding="utf-8")
    try:
        run_release()
        report2 = json.loads((DIST / "nuget-report.json").read_text(encoding="utf-8"))
        assert report2["legacy_cleared"] is False
    finally:
        notes_path.write_text(expected_notes, encoding="utf-8")
        run_release()
        restored = json.loads((DIST / "nuget-report.json").read_text(encoding="utf-8"))
        assert restored["legacy_cleared"] is True
        assert notes_path.read_text(encoding="utf-8") == expected_notes


def test_ledger_marker(release_dist: Path) -> None:
    """dist/ledger marker must contain publish-ready."""
    _ = release_dist
    assert (DIST / "ledger").read_text(encoding="utf-8") == "publish-ready\n"


def test_nuget_props_and_config(release_dist: Path) -> None:
    """Directory.Packages.props versions are 1.2.0 and nuget.config is local-feed-only."""
    _ = release_dist
    props = (APP / "src" / "Ledger" / "Directory.Packages.props").read_text(encoding="utf-8")
    for pkg in ("Ledger.Core", "Ledger.Utils", "Ledger.Gateway", "Ledger.Metrics"):
        assert f'Include="{pkg}" Version="1.2.0"' in props
    cfg = (APP / "nuget.config").read_text(encoding="utf-8")
    assert 'value="/app/nuget-cache"' in cfg
    assert "<clear" in cfg


def test_offline_cargo(release_dist: Path) -> None:
    """Cargo config must keep offline = true for offline packaging."""
    _ = release_dist
    assert "offline = true" in (APP / ".cargo" / "config.toml").read_text(encoding="utf-8")


def test_bundles_manifest(release_dist: Path) -> None:
    """release-manifest package/workspace digests and lane share layouts are correct."""
    manifest = json.loads((release_dist / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["package"]["name"] == "nugetfix-cli"
    assert manifest["package"]["version"] == "1.59.0"
    assert manifest["hash"] == json.loads((release_dist / "nuget-report.json").read_text(encoding="utf-8"))
    assert [b["lane"] for b in manifest["bundles"]] == [r["lane"] for r in matrix_rows()]
    for row, entry in zip(matrix_rows(), manifest["bundles"], strict=True):
        lane = row["lane"]
        bundle = release_dist / "bundles" / f"nugetfix-{lane}"
        archive = release_dist / f"nugetfix-{lane}-linux-x86_64.tar.gz"
        preview = json.loads((bundle / "share" / "audit-preview.json").read_text(encoding="utf-8"))
        assert_lane_share_files(bundle, lane)
        assert entry["archive_sha256"] == sha256(archive)
        assert entry["binary_sha256"] == sha256(bundle / "bin" / "nugetfix")
        assert entry["policy_sha256"] == sha256(bundle / "share" / "lane-policy.json")
        assert entry["audit_preview_sha256"] == sha256(bundle / "share" / "audit-preview.json")
        assert entry["artifact_count"] == len(preview["artifacts"])
        assert entry["hold_count"] == preview["totals"]["hold"]
        assert entry["risk_score_total"] == preview["totals"]["risk_score_total"]


def test_workspace(release_dist: Path) -> None:
    """Manifest workspace embeds Cargo [package].name values (nugetfix-cli, not binary nugetfix)."""
    manifest = json.loads((release_dist / "release-manifest.json").read_text(encoding="utf-8"))
    root = tomllib.loads((APP / "Cargo.toml").read_text(encoding="utf-8"))
    wlicense = root["workspace"]["package"]["license"]
    wversion = root["workspace"]["package"]["version"]
    assert wversion == "1.59.0"
    expected = []
    for path in sorted((APP / "crates").glob("*/Cargo.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        pkg = data["package"]
        lic = pkg.get("license", wlicense)
        ver = pkg.get("version", wversion)
        if isinstance(lic, dict) and lic.get("workspace"):
            lic = wlicense
        if isinstance(ver, dict) and ver.get("workspace"):
            ver = wversion
        expected.append({"name": pkg["name"], "version": ver, "license": lic, "dependencies": sorted((data.get("dependencies") or {}).keys())})
    assert manifest["workspace"] == expected
    assert [w["name"] for w in manifest["workspace"]] == ["nugetfix-cli", "nugetfix-core", "nugetfix-graph"]


def test_checksums(release_dist: Path) -> None:
    """checksums.sha256 lists bare relative paths sorted with matching digests."""
    mapping = {}
    for line in (release_dist / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        assert not rel.startswith("./")
        mapping[rel] = digest
    expected = []
    for path in release_dist.rglob("*"):
        if path.is_file() and path.name != "checksums.sha256":
            rel = str(path.relative_to(release_dist)).replace("\\", "/")
            expected.append(rel)
            assert mapping[rel] == sha256(path)
    assert list(mapping) == sorted(expected)


def test_archive_reproducible(release_dist: Path) -> None:
    """Sealed lane archives stay byte-identical across a second release under SOURCE_DATE_EPOCH."""
    lane = matrix_rows()[0]["lane"]
    archive = release_dist / f"nugetfix-{lane}-linux-x86_64.tar.gz"
    first = sha256(archive)
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert any(n == f"nugetfix-{lane}" or n.startswith(f"nugetfix-{lane}/") for n in names)
    run_release()
    assert first == sha256(DIST / f"nugetfix-{lane}-linux-x86_64.tar.gz")


def test_packaging_ok(release_dist: Path) -> None:
    """Packaging temps and packaging.ok must stay under /app/.release-tmp."""
    _ = release_dist
    assert (APP / ".release-tmp" / "packaging.ok").read_text(encoding="utf-8") == "ok\n"


def expected_audit(lane: str, retention_hops: int) -> dict:
    edges = [r for r in csv.DictReader((FIXTURES / "data" / "graphs" / "edges.csv").open(encoding="utf-8")) if r["lane"] == lane]
    artifacts = [r["coordinate"] for r in csv.DictReader((FIXTURES / "data" / "graphs" / "artifacts.csv").open(encoding="utf-8")) if r["lane"] == lane]
    packages = [r for r in csv.DictReader((FIXTURES / "config" / "packages.csv").open(encoding="utf-8")) if r["lane"] == lane]
    cache = {r["digest"] for r in csv.DictReader((FIXTURES / "nuget-cache" / "index.csv").open(encoding="utf-8"))}
    pins = {r["name"]: r["digest"] for r in csv.DictReader((FIXTURES / "config" / "pins.csv").open(encoding="utf-8"))}
    feedtags = {r["name"]: r["expected_tag"] for r in csv.DictReader((FIXTURES / "config" / "feedtags.csv").open(encoding="utf-8"))}
    advisories = list(csv.DictReader((FIXTURES / "config" / "advisories.csv").open(encoding="utf-8")))
    xor_rows = [r for r in csv.DictReader((FIXTURES / "config" / "xor.csv").open(encoding="utf-8")) if r["lane"] == lane]
    bans = {r["coordinate"] for r in csv.DictReader((FIXTURES / "config" / "bans.csv").open(encoding="utf-8"))}
    peers = [r for r in csv.DictReader((FIXTURES / "config" / "peers.csv").open(encoding="utf-8")) if r["lane"] == lane]
    art_set = set(artifacts)
    holds: dict[str, dict[str, int]] = {a: {} for a in artifacts}

    def add(coord: str, reason: str, risk: int) -> None:
        if coord not in holds:
            return
        holds[coord][reason] = max(holds[coord].get(reason, 0), risk)

    for p in packages:
        if p["coordinate"] not in art_set:
            continue
        exp = feedtags.get(p["name"])
        if exp is not None and exp != p["platform_tag"]:
            add(p["coordinate"], f"feedtag:{p['coordinate']}:{exp}:{p['platform_tag']}", 42)
        exp_h = pins.get(p["name"])
        if exp_h is not None and exp_h != p["digest"]:
            add(p["coordinate"], f"hashdrift:{p['coordinate']}:{exp_h}:{p['digest']}", 43)
        if p["digest"] not in cache:
            add(p["coordinate"], f"cachemiss:{p['coordinate']}:{p['digest']}", 40)
    present = {p["name"]: p["coordinate"] for p in packages if p["coordinate"] in art_set}
    present_names = set(present)
    by_group: dict[str, set[str]] = defaultdict(set)
    for row in xor_rows:
        if row["package_name"] in present:
            by_group[row["group"]].add(row["package_name"])
    for group, names in by_group.items():
        if len(names) < 2:
            continue
        joined = "|".join(sorted(names))
        hold = f"xor:{group}:{joined}"
        for n in names:
            add(present[n], hold, 52)
    for peer in peers:
        if peer["coordinate"] in art_set and peer["peer_name"] not in present_names:
            add(peer["coordinate"], f"packagerefdrift:{peer['coordinate']}:{peer['peer_name']}", 41)
    for adv in advisories:
        if adv["coordinate"] in art_set:
            add(adv["coordinate"], f"advisory:{adv['coordinate']}:{adv['cve']}", 49)
    for a in artifacts:
        if a in bans:
            add(a, f"ban:{a}", 55)
    origin_holds: dict[str, list[tuple[str, int]]] = {}
    for coord, hmap in holds.items():
        for reason, risk in hmap.items():
            if reason.startswith(("ban:", "xor:", "packagerefdrift:")):
                origin_holds.setdefault(coord, []).append((reason, risk))
    rev_map: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["edge_kind"] == "hard":
            rev_map[e["child"]].append(e["parent"])
    # Lex-smallest-parent spine + lex-smallest-origin collapse.
    best: dict[tuple[str, str], tuple[str, int]] = {}
    for origin, oh in origin_holds.items():
        node = origin
        visited = {origin}
        for _dist in range(retention_hops):
            parents = sorted(rev_map.get(node, []))
            if not parents:
                break
            parent = parents[0]
            if parent in visited:
                break
            visited.add(parent)
            for reason, risk in oh:
                key = (parent, reason)
                prev = best.get(key)
                if prev is None or origin < prev[0]:
                    best[key] = (origin, risk)
            node = parent
    for (parent, reason), (origin, risk) in best.items():
        add(parent, f"cascade:{origin}:{reason}", risk)
    reports = []
    totals = {
        "release": 0, "hold": 0, "feedtags": 0, "hashdrifts": 0, "cachemisses": 0,
        "xors": 0, "advisories": 0, "bans": 0, "packagerefdrifts": 0, "cascades": 0, "risk_score_total": 0,
    }
    for coord in sorted(artifacts):
        hmap = holds.get(coord, {})
        hold_list = sorted(hmap)
        score = sum(hmap[h] for h in hold_list)
        for h in hold_list:
            if h.startswith("feedtag:"):
                totals["feedtags"] += 1
            elif h.startswith("hashdrift:"):
                totals["hashdrifts"] += 1
            elif h.startswith("cachemiss:"):
                totals["cachemisses"] += 1
            elif h.startswith("xor:"):
                totals["xors"] += 1
            elif h.startswith("advisory:"):
                totals["advisories"] += 1
            elif h.startswith("ban:"):
                totals["bans"] += 1
            elif h.startswith("packagerefdrift:"):
                totals["packagerefdrifts"] += 1
            elif h.startswith("cascade:"):
                totals["cascades"] += 1
        status = "release" if not hold_list else "hold"
        totals[status] += 1
        totals["risk_score_total"] += score
        reports.append({"coordinate": coord, "status": status, "holds": hold_list, "risk_score": score})
    return {"lane": lane, "retention_hops": retention_hops, "artifacts": reports, "totals": totals}


@pytest.mark.parametrize("row", matrix_rows(), ids=lambda r: r["lane"])
def test_audit_preview(release_dist: Path, row: dict[str, str]) -> None:
    """Packaged audit-preview matches live binary and fixture-derived expected holds."""
    hops = int(row["retention_hops"])
    lane = row["lane"]
    bundle = release_dist / "bundles" / f"nugetfix-{lane}"
    preview = json.loads((bundle / "share" / "audit-preview.json").read_text(encoding="utf-8"))
    expected = expected_audit(lane, hops)
    live_share = run_packaged_audit(bundle, lane, hops, bundle / "share")
    with tempfile.TemporaryDirectory() as tmp:
        ctrl = Path(tmp)
        materialize_lane_share(lane, ctrl)
        live_ctrl = run_packaged_audit(bundle, lane, hops, ctrl)
    assert preview == expected
    assert live_share == expected
    assert live_ctrl == expected


@pytest.mark.parametrize("row", matrix_rows(), ids=lambda r: r["lane"])
def test_run_smoke(release_dist: Path, row: dict[str, str]) -> None:
    """run-smoke.sh is POSIX sh, passes cache/feedtags/peers, and accepts spaced outfile paths."""
    lane = row["lane"]
    hops = int(row["retention_hops"])
    bundle = release_dist / "bundles" / f"nugetfix-{lane}"
    script = bundle / "share" / "run-smoke.sh"
    assert os.access(script, os.X_OK)
    body = script.read_text(encoding="utf-8")
    assert body.startswith("#!/bin/sh")
    assert "pipefail" not in body
    assert "--cache" in body and "--feedtags" in body and "--peers" in body
    assert 'OUT=${1:-"$HERE/share/audit-preview.json"}' in body
    preview = bundle / "share" / "audit-preview.json"
    expected = json.loads(preview.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="nuget smoke ") as tmp:
        custom = Path(tmp) / "custom preview.json"
        subprocess.run(["sh", str(script), str(custom)], check=True, timeout=120)
        assert json.loads(custom.read_text(encoding="utf-8")) == expected
    subprocess.run(["sh", str(script)], check=True, timeout=120)
    assert json.loads(preview.read_text(encoding="utf-8")) == expected
    if lane == "edge":
        assert hops == 32
    if lane == "gate":
        assert hops == 3


def test_soft_edges_ignored(release_dist: Path) -> None:
    """Soft edges do not cascade; lex spine climbs arch→apex→vale→…→heath→dune→…; hops=32; triple bans."""
    preview = json.loads(
        (release_dist / "bundles" / "nugetfix-edge" / "share" / "audit-preview.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(preview.keys()) == {"lane", "retention_hops", "artifacts", "totals"}
    assert preview["lane"] == "edge"
    assert preview["retention_hops"] == 32
    coords = [a["coordinate"] for a in preview["artifacts"]]
    assert coords == sorted(coords), "audit-preview artifacts must be sorted by coordinate"
    assert coords.index("mid:arch") < coords.index("mid:stem")
    assert coords.index("mid:crest") < coords.index("mid:stem")
    assert coords.index("mid:peak") < coords.index("mid:stem")
    assert coords.index("mid:saddle") < coords.index("mid:stem")
    assert coords.index("mid:knoll") < coords.index("mid:stem")
    assert coords.index("mid:col") < coords.index("mid:stem")
    assert coords.index("mid:mesa") < coords.index("mid:stem")
    assert coords.index("mid:crag") < coords.index("mid:stem")
    assert coords.index("mid:rift") < coords.index("mid:stem")
    assert coords.index("mid:bridge") < coords.index("mid:spur")
    assert coords.index("mid:arch") < coords.index("mid:link")
    by = {a["coordinate"]: a for a in preview["artifacts"]}
    assert {
        "mid:link",
        "mid:arch",
        "mid:apex",
        "mid:heath",
        "mid:scar",
        "mid:mere",
        "mid:holt",
        "mid:vale",
        "mid:dune",
        "mid:rift",
        "mid:crag",
        "mid:tor",
        "mid:keel",
        "mid:mesa",
        "mid:glen",
        "mid:col",
        "mid:knoll",
        "mid:saddle",
        "mid:peak",
        "mid:cairn",
        "mid:crest",
        "mid:shelf",
        "mid:ledge",
        "mid:ford",
        "mid:ridge",
        "mid:stem",
        "mid:span",
        "mid:via",
        "mid:fork",
        "mid:wing",
        "mid:yoke",
        "mid:beam",
        "mid:spur",
        "mid:fen",
        "mid:bridge",
        "mid:relay",
        "trace:haze",
        "trace:mist",
        "trace:fog",
    }.issubset(by)
    edges_text = (APP / "data" / "graphs" / "edges.csv").read_text(encoding="utf-8")
    assert "edge,mid:spur,mid:fen,soft" in edges_text
    assert "edge,mid:holt,mid:vale,soft" in edges_text
    assert "edge,mid:mere,mid:holt,soft" not in edges_text
    soft_i = edges_text.index("edge,mid:spur,mid:fen,soft")
    holt_soft_i = edges_text.index("edge,mid:holt,mid:vale,soft")
    link_i = edges_text.index("edge,mid:link,pkg:blocked,hard")
    assert soft_i < link_i, "soft spur→fen must precede mid:link residual children"
    assert holt_soft_i < link_i, "soft holt→vale must precede mid:link residual children"
    assert not any(h.startswith("cascade:") for h in by["trace:soft"]["holds"])
    assert not any(h.startswith("cascade:") for h in by["mid:fen"]["holds"])
    assert not any(h.startswith("cascade:") for h in by["trace:haze"]["holds"])
    assert not any(h.startswith("cascade:") for h in by["trace:mist"]["holds"])
    assert not any(h.startswith("cascade:") for h in by["trace:fog"]["holds"])
    for origin in ("pkg:tainted", "pkg:blocked", "pkg:quarantine"):
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:link"]["holds"])
        for mid in (
            "mid:arch",
            "mid:apex",
            "mid:vale",
            "mid:holt",
            "mid:mere",
            "mid:scar",
            "mid:heath",
            "mid:dune",
            "mid:rift",
            "mid:crag",
            "mid:tor",
            "mid:keel",
            "mid:mesa",
            "mid:glen",
            "mid:col",
            "mid:knoll",
            "mid:saddle",
            "mid:peak",
            "mid:cairn",
            "mid:crest",
            "mid:shelf",
            "mid:ledge",
            "mid:ford",
            "mid:ridge",
            "mid:stem",
            "mid:span",
            "mid:relay",
            "mid:beam",
            "mid:spur",
            "mid:bridge",
            "svc:app",
        ):
            assert any(h.startswith(f"cascade:{origin}:ban:") for h in by[mid]["holds"])
        for mid in ("mid:via", "mid:fork", "mid:wing", "mid:yoke"):
            assert not any(h.startswith(f"cascade:{origin}:ban:") for h in by[mid]["holds"])
    policy = json.loads(
        (release_dist / "bundles" / "nugetfix-edge" / "share" / "lane-policy.json").read_text(
            encoding="utf-8"
        )
    )
    assert policy == {"lane": "edge", "retention_hops": 32}


def test_diamond_lex_spine(release_dist: Path) -> None:
    """Five-arm fan uses lex-smallest parent (mid:arch); via/fork/wing/yoke stay off-spine."""
    preview = json.loads(
        (release_dist / "bundles" / "nugetfix-edge" / "share" / "audit-preview.json").read_text(
            encoding="utf-8"
        )
    )
    by = {a["coordinate"]: a for a in preview["artifacts"]}
    assert "mid:via" in by and "mid:fork" in by and "mid:wing" in by and "mid:yoke" in by
    assert (
        "mid:arch" in by
        and "mid:heath" in by
        and "mid:dune" in by
        and "mid:rift" in by
        and "mid:crag" in by
        and "mid:tor" in by
        and "mid:keel" in by
        and "mid:mesa" in by
        and "mid:glen" in by
        and "mid:col" in by
        and "mid:knoll" in by
        and "mid:saddle" in by
        and "mid:peak" in by
        and "mid:cairn" in by
        and "mid:crest" in by
        and "mid:ford" in by
        and "mid:beam" in by
        and "mid:spur" in by
    )
    for origin in ("pkg:tainted", "pkg:blocked", "pkg:quarantine"):
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:arch"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:heath"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:dune"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:rift"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:keel"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:glen"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:ford"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:beam"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:crag"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:tor"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:mesa"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:col"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:knoll"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:saddle"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:peak"]["holds"])
        assert any(h.startswith(f"cascade:{origin}:ban:") for h in by["svc:app"]["holds"])
        assert not any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:via"]["holds"])
        assert not any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:fork"]["holds"])
        assert not any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:wing"]["holds"])
        assert not any(h.startswith(f"cascade:{origin}:ban:") for h in by["mid:yoke"]["holds"])


def test_residuals_present(release_dist: Path) -> None:
    """Edge keeps triple bans/advisory/packagerefdrift; gate keeps alt-a/alt-b xor with g1/g2 hops."""
    edge = json.loads(
        (release_dist / "bundles" / "nugetfix-edge" / "share" / "audit-preview.json").read_text(
            encoding="utf-8"
        )
    )
    by_edge = {a["coordinate"]: a for a in edge["artifacts"]}
    assert any(h.startswith("ban:") for h in by_edge["pkg:tainted"]["holds"])
    assert any(h.startswith("ban:") for h in by_edge["pkg:blocked"]["holds"])
    assert any(h.startswith("ban:") for h in by_edge["pkg:quarantine"]["holds"])
    assert any(h.startswith("advisory:") for h in by_edge["pkg:legacy-nuget"]["holds"])
    assert "packagerefdrift:pkg:ledger-gateway:ledger-extra" in by_edge["pkg:ledger-gateway"]["holds"]
    assert any(h.startswith("cascade:pkg:ledger-gateway:packagerefdrift:") for h in by_edge["svc:app"]["holds"])
    assert any(h.startswith("cascade:pkg:tainted:ban:") for h in by_edge["svc:app"]["holds"])
    assert any(h.startswith("cascade:pkg:blocked:ban:") for h in by_edge["svc:app"]["holds"])
    assert any(h.startswith("cascade:pkg:quarantine:ban:") for h in by_edge["svc:app"]["holds"])
    assert (
        "mid:arch" in by_edge
        and "mid:heath" in by_edge
        and "mid:dune" in by_edge
        and "mid:rift" in by_edge
        and "mid:crag" in by_edge
        and "mid:tor" in by_edge
        and "mid:keel" in by_edge
        and "mid:mesa" in by_edge
        and "mid:glen" in by_edge
        and "mid:col" in by_edge
        and "mid:knoll" in by_edge
        and "mid:saddle" in by_edge
        and "mid:peak" in by_edge
        and "mid:cairn" in by_edge
        and "mid:crest" in by_edge
        and "mid:ford" in by_edge
        and "mid:beam" in by_edge
        and "mid:spur" in by_edge
        and "trace:haze" in by_edge
        and "trace:mist" in by_edge
        and "trace:fog" in by_edge
        and "mid:scar" in by_edge
        and "mid:vale" in by_edge
    )
    xor_text = (APP / "config" / "xor.csv").read_text(encoding="utf-8")
    assert "edge,unused,ledger-utils" in xor_text
    assert "gate,mgr-choice,alt-a" in xor_text

    gate = json.loads(
        (release_dist / "bundles" / "nugetfix-gate" / "share" / "audit-preview.json").read_text(
            encoding="utf-8"
        )
    )
    by_gate = {a["coordinate"]: a for a in gate["artifacts"]}
    assert any(h.startswith("xor:mgr-choice:") for h in by_gate["pkg:alt-a"]["holds"])
    assert any(h.startswith("xor:mgr-choice:") for h in by_gate["pkg:alt-b"]["holds"])
    assert "xor:mgr-choice:alt-a|alt-b" in by_gate["pkg:alt-a"]["holds"]
    assert "mid:g1" in by_gate and "mid:g2" in by_gate
    assert any(h.startswith("cascade:pkg:alt-a:xor:") for h in by_gate["gw:edge"]["holds"])
    assert any(h.startswith("cascade:pkg:alt-a:xor:") for h in by_gate["mid:g1"]["holds"])
    assert any(h.startswith("cascade:pkg:alt-a:xor:") for h in by_gate["mid:g2"]["holds"])
    assert not any(h.startswith("cascade:pkg:alt-b:xor:") for h in by_gate["gw:edge"]["holds"])


def test_primary_packages_clean(release_dist: Path) -> None:
    """Primary packages have no feedtag/hashdrift/cachemiss holds (packagerefdrift on ledger-gateway allowed)."""
    for row in matrix_rows():
        preview = json.loads(
            (
                release_dist / "bundles" / f"nugetfix-{row['lane']}" / "share" / "audit-preview.json"
            ).read_text(encoding="utf-8")
        )
        by = {a["coordinate"]: a for a in preview["artifacts"]}
        for coord in ("pkg:ledger-core", "pkg:ledger-utils", "pkg:ledger-gateway", "pkg:ledger-metrics"):
            if coord in by:
                assert not any(h.startswith(("feedtag:", "hashdrift:", "cachemiss:")) for h in by[coord]["holds"])
                if coord != "pkg:ledger-gateway":
                    assert not any(h.startswith("packagerefdrift:") for h in by[coord]["holds"])


def test_no_unpacked_at_root(release_dist: Path) -> None:
    """Unpacked lane trees live only under dist/bundles."""
    for path in release_dist.iterdir():
        if path.is_dir():
            assert path.name == "bundles"


def _fail_closed_run() -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CARGO_NET_OFFLINE"] = "true"
    env["SOURCE_DATE_EPOCH"] = "1700000000"
    return subprocess.run(
        ["bash", "/app/scripts/release.sh"],
        cwd=APP,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=360,
    )


def test_fail_closed_soft_spur_fen(release_dist: Path) -> None:
    """Missing soft spur→fen decoy must abort with fail-closed before dist rewrite."""
    _ = release_dist
    edges = APP / "data" / "graphs" / "edges.csv"
    original = edges.read_text(encoding="utf-8")
    marker = (DIST / "nuget-guard.txt").read_text(encoding="utf-8")
    try:
        edges.write_text(original.replace("edge,mid:spur,mid:fen,soft\n", ""), encoding="utf-8")
        result = _fail_closed_run()
        assert result.returncode != 0
        assert "fail-closed" in ((result.stderr or "") + (result.stdout or ""))
        assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == marker
    finally:
        edges.write_text(original, encoding="utf-8")
        run_release()


def test_fail_closed_soft_holt_vale(release_dist: Path) -> None:
    """Missing soft holt→vale decoy must abort with fail-closed before dist rewrite."""
    _ = release_dist
    edges = APP / "data" / "graphs" / "edges.csv"
    original = edges.read_text(encoding="utf-8")
    marker = (DIST / "nuget-guard.txt").read_text(encoding="utf-8")
    try:
        edges.write_text(original.replace("edge,mid:holt,mid:vale,soft\n", ""), encoding="utf-8")
        result = _fail_closed_run()
        assert result.returncode != 0
        assert "fail-closed" in ((result.stderr or "") + (result.stdout or ""))
        assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == marker
    finally:
        edges.write_text(original, encoding="utf-8")
        run_release()


def test_fail_closed_soft_after_link(release_dist: Path) -> None:
    """Soft decoys after mid:link residual children must abort fail-closed."""
    _ = release_dist
    edges = APP / "data" / "graphs" / "edges.csv"
    original = edges.read_text(encoding="utf-8")
    marker = (DIST / "nuget-guard.txt").read_text(encoding="utf-8")
    try:
        moved = original.replace("edge,mid:spur,mid:fen,soft\n", "")
        moved = moved.replace(
            "edge,mid:link,pkg:tainted,hard\n",
            "edge,mid:link,pkg:tainted,hard\nedge,mid:spur,mid:fen,soft\n",
        )
        edges.write_text(moved, encoding="utf-8")
        result = _fail_closed_run()
        assert result.returncode != 0
        assert "fail-closed" in ((result.stderr or "") + (result.stdout or ""))
        assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == marker
    finally:
        edges.write_text(original, encoding="utf-8")
        run_release()


def test_fail_closed_spine_root(release_dist: Path) -> None:
    """First hard edge hop not svc:app→mid:bridge must abort fail-closed."""
    _ = release_dist
    edges = APP / "data" / "graphs" / "edges.csv"
    original = edges.read_text(encoding="utf-8")
    marker = (DIST / "nuget-guard.txt").read_text(encoding="utf-8")
    try:
        edges.write_text(
            original.replace(
                "edge,svc:app,mid:bridge,hard\nedge,mid:bridge,mid:spur,hard\n",
                "edge,mid:bridge,mid:spur,hard\nedge,svc:app,mid:bridge,hard\n",
                1,
            ),
            encoding="utf-8",
        )
        result = _fail_closed_run()
        assert result.returncode != 0
        assert "fail-closed" in ((result.stderr or "") + (result.stdout or ""))
        assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == marker
    finally:
        edges.write_text(original, encoding="utf-8")
        run_release()


def test_fail_closed_nuget_config(release_dist: Path) -> None:
    """nuget.config without local cache feed must abort fail-closed."""
    _ = release_dist
    path = APP / "nuget.config"
    original = path.read_text(encoding="utf-8")
    marker = (DIST / "nuget-guard.txt").read_text(encoding="utf-8")
    try:
        path.write_text(original.replace('/app/nuget-cache', '/tmp/other-feed'), encoding="utf-8")
        result = _fail_closed_run()
        assert result.returncode != 0
        assert "fail-closed" in ((result.stderr or "") + (result.stdout or ""))
        assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == marker
    finally:
        path.write_text(original, encoding="utf-8")
        run_release()


def test_fail_closed_workspace_version(release_dist: Path) -> None:
    """Cargo.toml workspace version other than 1.59.0 must abort with fail-closed."""
    _ = release_dist
    path = APP / "Cargo.toml"
    original = path.read_text(encoding="utf-8")
    marker = (DIST / "nuget-guard.txt").read_text(encoding="utf-8")
    try:
        path.write_text(original.replace("1.59.0", "0.18.0", 1), encoding="utf-8")
        result = _fail_closed_run()
        assert result.returncode != 0
        assert "fail-closed" in ((result.stderr or "") + (result.stdout or ""))
        assert (DIST / "nuget-guard.txt").read_text(encoding="utf-8") == marker
    finally:
        path.write_text(original, encoding="utf-8")
        run_release()
