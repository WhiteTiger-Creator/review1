"""Domain checks for memcg peak journal reload report."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

OUT = Path("/app/output/peak_report.json")
ROOT = Path("/app/environment")
UNIT = ROOT / "systemd" / "hwm-unit@.service"
APP_BIN = Path("/app/bin/hwm_drive")
TESTS = Path(os.environ.get("TEST_DIR", "/tests"))
HELDOUT = TESTS / "heldout"
MANIFEST = TESTS / "input_manifest.json"
NONCE_FILE = TESTS / "verifier_nonce"
VERIFIER_BIN = Path("/tmp/verifier-hwm_drive")
PRIMARY = ("oak", "pine", "ash")
HOLDOUT = "elm"
TIGHT = 48
WIDE = 96
LANE_SAMPLES = (
    ("oak", "r1.jsonl"),
    ("pine", "r2.jsonl"),
    ("ash", "r3.jsonl"),
    ("elm", "r4.jsonl"),
)

AGENT_ENV = {
    "HOME": "/tmp",
    "PATH": os.environ.get("PATH", "/bin"),
    "GOPATH": "/tmp/go",
    "GOMODCACHE": "/tmp/go/pkg/mod",
}


def _harden_verifier_fs() -> None:
    """Lock /tests so the dropped agent uid cannot read verifier material."""
    if TESTS.is_dir() and os.geteuid() == 0:
        for root, _dirs, files in os.walk(TESTS):
            os.chown(root, 0, 0)
            os.chmod(root, 0o700)
            for name in files:
                fp = Path(root) / name
                os.chown(fp, 0, 0)
                os.chmod(fp, 0o600)


_harden_verifier_fs()


def _world_writable(path: Path) -> None:
    mode = path.stat().st_mode
    os.chmod(path, mode | stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)


def _prepare_workspace() -> None:
    out_dir = Path("/app/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = out_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    _world_writable(out_dir)
    _world_writable(scratch)
    bin_dir = Path("/app/bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    _world_writable(bin_dir)


def _run_agent(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run candidate tooling as an unprivileged uid that cannot read /tests."""
    check = kwargs.pop("check", False)
    return subprocess.run(
        cmd,
        user="nobody",
        group="nogroup",
        env=AGENT_ENV,
        check=check,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _sha256(target: Path) -> str:
    proc = subprocess.run(
        ["sha256sum", str(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.split()[0]


def _page_delta() -> int:
    """Verifier-only bump applied to live samples so fixed report rows cannot pass."""
    raw = NONCE_FILE.read_text(encoding="utf-8").strip()
    assert raw, "missing verifier nonce"
    n = 0
    for ch in raw:
        n = (n * 33 + ord(ch)) & 0xFFFFFFFF
    return (n % 5) + 1


def _restore_and_seal_fixtures() -> None:
    """Restore graded fixtures from heldout copies and enforce sealed digests."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = manifest["files"]
    assert files, "input manifest must list protected inputs"
    for rel, want_hash in files.items():
        pinned = HELDOUT / rel
        live = ROOT / rel
        assert pinned.is_file(), f"missing heldout input {pinned}"
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_bytes(pinned.read_bytes())
        live_digest = _sha256(live)
        pinned_digest = _sha256(pinned)
        assert pinned_digest == want_hash, f"tampered heldout input {rel}"
        assert live_digest == want_hash, f"tampered live input {rel}"


def _mutate_live_samples() -> int:
    """Perturb live sample streams after seal restore; returns the applied delta."""
    delta = _page_delta()
    for _lane, fname in LANE_SAMPLES:
        sample_file = ROOT / "fixtures" / "samples" / fname
        lines = [ln for ln in sample_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) > 3, f"sample stream too short: {fname}"
        rec = json.loads(lines[3])
        rec["pages"] = int(rec["pages"]) + delta
        lines[3] = json.dumps(rec, separators=(",", ":"))
        sample_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return delta


def _rebuild_driver() -> Path:
    """Rebuild hwm_drive from submitted sources into the unit ExecStart binary path."""
    if VERIFIER_BIN.exists():
        VERIFIER_BIN.unlink()
    proc = subprocess.run(
        ["go", "build", "-o", str(VERIFIER_BIN), "./cmd/hwm_drive"],
        cwd=ROOT,
        env={**os.environ, **AGENT_ENV},
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    os.chmod(VERIFIER_BIN, 0o755)
    APP_BIN.parent.mkdir(parents=True, exist_ok=True)
    _world_writable(APP_BIN.parent)
    shutil.copy2(VERIFIER_BIN, APP_BIN)
    os.chmod(APP_BIN, 0o755)
    return APP_BIN


def _unit_execstart_argv() -> list[str]:
    """Parse and validate the lane unit ExecStart against the public unit contract."""
    assert UNIT.is_file(), f"missing unit template {UNIT}"
    text = UNIT.read_text(encoding="utf-8")
    exec_line = None
    for line in text.splitlines():
        if line.startswith("ExecStart="):
            exec_line = line.split("=", 1)[1].strip()
            break
    assert exec_line, "unit template missing ExecStart"
    argv = exec_line.split()
    assert argv[0] == str(APP_BIN), f"ExecStart binary must be {APP_BIN}"
    assert "--root" in argv and str(ROOT) in argv
    assert "--out" in argv and str(OUT) in argv
    return argv


def _run_matrix(*, wide: bool = False) -> tuple[subprocess.CompletedProcess, int]:
    _prepare_workspace()
    _restore_and_seal_fixtures()
    delta = _mutate_live_samples()
    _rebuild_driver()
    unit_argv = _unit_execstart_argv()
    prep = _run_agent(["bash", str(ROOT / "scripts" / "prep_run.sh")])
    assert prep.returncode == 0, prep.stderr + prep.stdout
    cmd = list(unit_argv)
    if wide:
        cmd.append("--wide")
    return _run_agent(cmd), delta


def _load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8"))


def _by_mode(report: dict) -> dict[tuple[str, str], dict]:
    out = {}
    for row in report["cases"]:
        out[(row["slice_id"], row["path_mode"])] = row
    return out


def _members(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _roster(slice_id: str) -> tuple[int, dict[str, str]] | None:
    roster_file = ROOT / "fixtures" / "roster" / f"{slice_id}.json"
    if not roster_file.exists():
        return None
    raw = json.loads(roster_file.read_text(encoding="utf-8"))
    return int(raw["after"]), {str(k): str(v) for k, v in raw["patch"].items()}


def _peak_from_samples(
    sample: Path, lane: str, mem: dict[int, str], plan: tuple[int, dict[str, str]] | None
) -> int:
    live: dict[int, int] = {}
    peak = 0
    lines = [ln for ln in sample.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for i, raw in enumerate(lines):
        if plan is not None and i == plan[0]:
            for pid_s, dest in plan[1].items():
                mem[int(pid_s)] = dest
            live = {pid: pages for pid, pages in live.items() if mem.get(pid) == lane}
        rec = json.loads(raw)
        pid = int(rec["pid"])
        pages = int(rec["pages"])
        if mem.get(pid) != lane:
            continue
        live[pid] = pages
        total = sum(live.values())
        peak = max(peak, total)
    return peak


def _expected_clean(wide: bool = False) -> dict[str, int]:
    """Recompute from live (mutated) fixtures the driver actually consumed."""
    mem_path = ROOT / "fixtures" / "members" / ("map_b.json" if wide else "map_a.json")
    out: dict[str, int] = {}
    for lane, fname in LANE_SAMPLES:
        mem = _members(mem_path)
        out[lane] = _peak_from_samples(
            ROOT / "fixtures" / "samples" / fname,
            lane,
            mem,
            _roster(lane),
        )
    return out


def _parse_journal(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _assert_scratch_binds_live(*, wide: bool = False) -> None:
    """Journal/checkpoint must reflect live fixtures, not placeholder stubs."""
    scratch = Path("/app/output/scratch")
    jnl = scratch / "hwm.jnl"
    ckpt = scratch / "hwm.ckpt"
    assert jnl.is_file() and jnl.stat().st_size > 0
    assert ckpt.is_file() and ckpt.stat().st_size > 0
    recs = _parse_journal(jnl)
    kinds = {r.get("kind") for r in recs}
    assert "sample" in kinds
    assert "fence" in kinds
    assert "roster" in kinds

    samples = [r for r in recs if r.get("kind") == "sample"]
    rosters = [r for r in recs if r.get("kind") == "roster"]
    fences = [r for r in recs if r.get("kind") == "fence"]
    assert len(fences) >= 4

    cursor = 0
    for lane, fname in LANE_SAMPLES:
        live_lines = [
            json.loads(ln)
            for ln in (ROOT / "fixtures" / "samples" / fname).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        for want in live_lines:
            matched = False
            while cursor < len(samples):
                got = samples[cursor]
                cursor += 1
                if (
                    got.get("lane") == lane
                    and int(got.get("pid", -1)) == int(want["pid"])
                    and int(got.get("pages", -1)) == int(want["pages"])
                ):
                    matched = True
                    break
            assert matched, f"journal missing live sample lane={lane} {want}"
        plan = _roster(lane)
        if plan is not None:
            assert any(
                r.get("lane") == lane and r.get("patch") == plan[1] for r in rosters
            ), f"journal missing roster for {lane}"

    hint = json.loads(ckpt.read_text(encoding="utf-8"))
    assert isinstance(hint.get("peaks"), dict)
    assert "gen" in hint
    # Checkpoint raw tallies must not equal graded clean peaks for every lane.
    exp = _expected_clean(wide)
    raw_peaks = {k: int(v) for k, v in hint["peaks"].items()}
    assert any(raw_peaks.get(lane, -1) != exp[lane] for lane in exp), (
        "checkpoint peaks look pre-baked to graded values"
    )


def _heldout_baseline_peak(lane: str, fname: str) -> int:
    mem = _members(HELDOUT / "fixtures" / "members" / "map_a.json")
    plan_path = HELDOUT / "fixtures" / "roster" / f"{lane}.json"
    plan = None
    if plan_path.exists():
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        plan = (int(raw["after"]), {str(k): str(v) for k, v in raw["patch"].items()})
    return _peak_from_samples(
        HELDOUT / "fixtures" / "samples" / fname,
        lane,
        mem,
        plan,
    )


def _assert_report_uses_delta(report: dict, delta: int) -> None:
    """Fixed unmutated answers cannot survive the verifier-only sample bump."""
    assert delta >= 1
    rows = _by_mode(report)
    base = _heldout_baseline_peak("oak", "r1.jsonl")
    assert rows[("oak", "clean")]["peak_pages"] == base + delta


@pytest.fixture(scope="module")
def report_bundle():
    _harden_verifier_fs()
    proc, delta = _run_matrix()
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert OUT.exists()
    rep = _load()
    _assert_scratch_binds_live(wide=False)
    _assert_report_uses_delta(rep, delta)
    exp = _expected_clean(False)
    return {"report": rep, "exp": exp, "delta": delta}


@pytest.fixture(scope="module")
def report(report_bundle):
    return report_bundle["report"]


def test_q0_tests_not_readable_by_agent():
    """Dropped agent uid cannot read verifier-only material under /tests."""
    _harden_verifier_fs()
    proc = _run_agent(["/bin/cat", str(MANIFEST)])
    assert proc.returncode != 0
    proc2 = _run_agent(["/bin/cat", str(HELDOUT / "fixtures" / "members" / "map_a.json")])
    assert proc2.returncode != 0
    proc3 = _run_agent(["/bin/cat", str(NONCE_FILE)])
    assert proc3.returncode != 0


def test_q0_fixture_seals():
    """Live graded fixtures match sealed heldout digests before mutation."""
    _restore_and_seal_fixtures()
    before = _sha256(ROOT / "fixtures" / "samples" / "r1.jsonl")
    delta = _mutate_live_samples()
    after = _sha256(ROOT / "fixtures" / "samples" / "r1.jsonl")
    assert delta >= 1
    assert before != after
    _restore_and_seal_fixtures()


def test_q0_unit_execstart():
    """Lane unit template ExecStart targets the installed driver binary and report path."""
    argv = _unit_execstart_argv()
    assert argv[0] == str(APP_BIN)
    assert UNIT.read_text(encoding="utf-8").count("ExecStart=") == 1


def test_q1_clean_cap(report):
    """Clean path rows for primary lanes stay under tight budget."""
    rows = _by_mode(report)
    for lane in PRIMARY:
        row = rows[(lane, "clean")]
        assert row["budget_cap"] == TIGHT
        assert row["peak_pages"] <= TIGHT
        assert row["harness_exit"] == 0


def test_q2_recompute_band(report_bundle):
    """Report clean peaks match independent live sample+membership+roster recompute."""
    rows = _by_mode(report_bundle["report"])
    for lane, want in report_bundle["exp"].items():
        assert rows[(lane, "clean")]["peak_pages"] == want


def test_q3_path_parity(report_bundle):
    """Mended peaks equal clean peaks per lane and match recomputed values."""
    rows = _by_mode(report_bundle["report"])
    exp = report_bundle["exp"]
    for lane in (*PRIMARY, HOLDOUT):
        assert rows[(lane, "mended")]["peak_pages"] == rows[(lane, "clean")]["peak_pages"]
        assert rows[(lane, "mended")]["peak_pages"] == exp[lane]
        assert rows[(lane, "clean")]["peak_pages"] == exp[lane]


def test_q4_handoff_isolation(report_bundle):
    """Reloaded peaks match clean peaks (no sticky prior high-water)."""
    rows = _by_mode(report_bundle["report"])
    exp = report_bundle["exp"]
    for lane in PRIMARY:
        assert rows[(lane, "reloaded")]["peak_pages"] == rows[(lane, "clean")]["peak_pages"]
        assert rows[(lane, "reloaded")]["peak_pages"] == exp[lane]
        assert rows[(lane, "reloaded")]["harness_exit"] == 0
        assert rows[(lane, "reloaded")]["budget_cap"] == TIGHT


def test_q5_holdout_arm(report):
    """Holdout elm appears on clean and mended under budget."""
    rows = _by_mode(report)
    for mode in ("clean", "mended"):
        row = rows[(HOLDOUT, mode)]
        assert row["peak_pages"] <= TIGHT
        assert row["harness_exit"] == 0
    assert (HOLDOUT, "reloaded") not in rows


def test_q6_wide_arm():
    """Wide arm uses budget_cap 96 with full clean/mended/reloaded coverage."""
    _run_agent(["bash", str(ROOT / "migrations" / "mig9.sh")], check=True)
    proc, delta = _run_matrix(wide=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    rep = _load()
    _assert_scratch_binds_live(wide=True)
    _assert_report_uses_delta(rep, delta)
    exp = _expected_clean(True)
    rows = _by_mode(rep)
    for lane in PRIMARY:
        for mode in ("clean", "mended", "reloaded"):
            assert rows[(lane, mode)]["budget_cap"] == WIDE
            assert rows[(lane, mode)]["peak_pages"] == exp[lane]
            assert rows[(lane, mode)]["harness_exit"] == 0
        assert rows[(lane, "mended")]["peak_pages"] == rows[(lane, "clean")]["peak_pages"]
        assert rows[(lane, "reloaded")]["peak_pages"] == rows[(lane, "clean")]["peak_pages"]
    for mode in ("clean", "mended"):
        assert rows[(HOLDOUT, mode)]["budget_cap"] == WIDE
        assert rows[(HOLDOUT, mode)]["peak_pages"] == exp[HOLDOUT]
        assert rows[(HOLDOUT, mode)]["harness_exit"] == 0
    assert rows[(HOLDOUT, "mended")]["peak_pages"] == rows[(HOLDOUT, "clean")]["peak_pages"]
    assert (HOLDOUT, "reloaded") not in rows


def test_q7_handwrite_fail():
    """Static JSON is overwritten; verifier-built driver must bind live fixtures and journal."""
    fake = {
        "schema": "peak_v1",
        "cases": [
            {
                "slice_id": "oak",
                "peak_pages": 1,
                "budget_cap": 48,
                "path_mode": "clean",
                "harness_exit": 0,
            }
        ],
    }
    OUT.write_text(json.dumps(fake, indent=2) + "\n", encoding="utf-8")
    scratch = Path("/app/output/scratch")
    if scratch.exists():
        for p in scratch.glob("*"):
            p.unlink()
    proc, delta = _run_matrix()
    assert proc.returncode == 0, proc.stderr + proc.stdout
    rep = _load()
    assert len(rep["cases"]) >= 8
    _assert_scratch_binds_live(wide=False)
    _assert_report_uses_delta(rep, delta)
    jnl = (scratch / "hwm.jnl").read_text(encoding="utf-8")
    assert re.search(r'"kind"\s*:\s*"roster"', jnl)
    exp = _expected_clean(False)
    rows = _by_mode(rep)
    assert rows[("oak", "clean")]["peak_pages"] == exp["oak"]
    assert rows[("oak", "mended")]["peak_pages"] == exp["oak"]
    assert rows[("pine", "clean")]["peak_pages"] == exp["pine"]
    assert rows[("ash", "mended")]["peak_pages"] == exp["ash"]
    assert rows[("elm", "clean")]["peak_pages"] == exp["elm"]


def test_q8_schema_rows(report):
    """Required schema and case fields match the public pact contract."""
    pact = (ROOT / "docs" / "pact_n4.md").read_text(encoding="utf-8")
    assert "peak_v1" in pact
    assert report["schema"] in pact
    assert isinstance(report["cases"], list)
    seen = set()
    modes = set()
    for row in report["cases"]:
        for key in ("slice_id", "peak_pages", "budget_cap", "path_mode", "harness_exit"):
            assert key in row
        assert isinstance(row["peak_pages"], int)
        assert isinstance(row["budget_cap"], int)
        assert isinstance(row["harness_exit"], int)
        modes.add(row["path_mode"])
        seen.add((row["slice_id"], row["path_mode"]))
    for token in ("clean", "mended", "reloaded"):
        assert token in pact
        assert token in modes
    for lane in PRIMARY:
        for mode in ("clean", "mended", "reloaded"):
            assert (lane, mode) in seen
    assert (HOLDOUT, "clean") in seen
    assert (HOLDOUT, "mended") in seen
    assert all(mode in modes for mode in ("clean", "mended", "reloaded"))


def test_q9_shallow_not_graded(report):
    """Shallow q9 interim file is not a substitute for the graded report."""
    haze = ROOT / "fixtures" / "q9" / "haze.json"
    assert haze.exists()
    stub = json.loads(haze.read_text(encoding="utf-8"))
    assert stub.get("schema") != report["schema"]
    rows = _by_mode(report)
    assert rows[("oak", "clean")]["peak_pages"] != stub.get("peak_pages", -1)
    assert len(report["cases"]) > 1
