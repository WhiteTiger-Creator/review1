import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

OUTPUT = Path("/app/output")
ENV = Path("/app/environment")
FIXTURES = ENV / "fixtures"
PAYLOAD = ENV / "data/seed_payload.bin"
DEFAULT_CYCLES = 2
LOGICAL_PATH = "mir-blk"
CONFIG_HOLD_MS = 1200
VERIFIER_BIN = Path(os.environ.get("VERIFIER_BIN", "/tmp/verifier-bin"))
VERIFIER_RUN_USER = os.environ.get("VERIFIER_RUN_USER", "mirrun")
REBUILD = ["bash", "/tests/rebuild_task_binaries.sh"]
VERIFIER_CYCLE = ["bash", "/tests/run_verifier_cycle.sh"]


def _verifier_cycle_env(**overrides: str) -> dict:
    env = os.environ.copy()
    env.update(
        OUTPUT_DIR=str(OUTPUT),
        CYCLE_COUNT=str(DEFAULT_CYCLES),
        VERIFIER_BIN=str(VERIFIER_BIN),
        MIRROR_ROOT=str(ENV),
    )
    env.update(overrides)
    return env


def _rebuild_from_submitted_sources() -> None:
    subprocess.run(["test", "-d", "/app/environment"], check=True)
    subprocess.run(["bash", "/tests/verify_infra.sh"], check=True)


@pytest.fixture(scope="session", autouse=True)
def _session_rebuild() -> None:
    _rebuild_from_submitted_sources()


def _mirctl() -> Path:
    return VERIFIER_BIN / "mirctl"


def _prepare_run_tree(root: Path, out: Path) -> None:
    subprocess.run(["chown", "-R", VERIFIER_RUN_USER, str(out)], check=False)
    if root == ENV:
        return
    parent = root
    while parent != parent.parent:
        subprocess.run(["chmod", "a+rx", str(parent)], check=False)
        if parent == Path("/"):
            break
        parent = parent.parent
    subprocess.run(["chmod", "-R", "a+rX", str(root)], check=False)
    subprocess.run(["chown", "-R", VERIFIER_RUN_USER, str(root)], check=False)


def _run_as(args: list[str], *, env: dict, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["runuser", "-u", VERIFIER_RUN_USER, "--", "env"]
    cmd.extend(f"{key}={value}" for key, value in env.items())
    cmd.extend(args)
    return subprocess.run(cmd, cwd="/app", check=check)


def _run_mirctl(
    out_dir: Path,
    *,
    mirror_root: Path | None = None,
    cycle: int | None = None,
    append: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    mirctl = _mirctl()
    assert mirctl.is_file() and os.access(mirctl, os.X_OK), f"missing verifier binary {mirctl}"
    env = {
        "MIRROR_ROOT": str(mirror_root or ENV),
        "OUTPUT_DIR": str(out_dir),
    }
    if cycle is not None:
        env["CYCLE"] = str(cycle)
    if append:
        env["APPEND_EXPORT"] = "1"
    _prepare_run_tree(Path(env["MIRROR_ROOT"]), out_dir)
    return _run_as([str(mirctl), "run", str(out_dir)], env=env, check=check)


def _catalog(cycle: int) -> dict:
    name = "catalog_view_a.json" if cycle == 1 else "catalog_view_b.json"
    return json.loads((FIXTURES / name).read_text())


def _probe(cycle: int) -> dict:
    name = "probe_view_a.json" if cycle == 1 else "probe_view_b.json"
    return json.loads((FIXTURES / name).read_text())


def _tally_hex(tally: int, epoch: int) -> str:
    canon = tally.to_bytes(8, "little", signed=False) + epoch.to_bytes(4, "little", signed=False)
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-hex"],
        input=canon,
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode().strip().split()[-1]


def _window_sum(offset: int, span: int) -> int:
    data = PAYLOAD.read_bytes()
    window = data[offset : offset + span]
    return sum(window)


def _run_repro(extra_env: dict | None = None) -> subprocess.CompletedProcess:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    env = _verifier_cycle_env(**(extra_env or {}))
    return subprocess.run(VERIFIER_CYCLE, cwd="/app", env=env, check=False)


def _load(name: str):
    path = OUTPUT / name
    assert path.exists(), f"missing {path}"
    if name.endswith(".jsonl"):
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    data = json.loads(path.read_text())
    if name == "push_trace.json":
        return data.get("segments", data)
    return data


def _side_b_view() -> dict:
    digest = _load("rolling_digest.json")
    side_b = [v for v in digest["views"] if v["source"] == "side-b"]
    assert side_b, "missing side-b view in rolling_digest"
    return side_b[0]


def _side_a_view() -> dict | None:
    digest = _load("rolling_digest.json")
    side_a = [v for v in digest["views"] if v["source"] == "side-a"]
    return side_a[0] if side_a else None


def _max_verified_seal(conv: dict) -> int:
    seal = 0
    for row in conv.get("cycles", []):
        if row["verified_bytes"] > 0 and row["verified_bytes"] == row["synced_bytes"]:
            seal = max(seal, row["cycle"])
    return seal


def _packed_probe_epoch(cycle: int) -> int:
    catalog = _catalog(cycle)
    probe = _probe(cycle)
    lanes = {"catalog_lane": 0, "probe_lane": 1}
    cat_epoch = catalog["epoch"]
    prb_epoch = probe["epoch"]
    if lanes["catalog_lane"] == lanes["probe_lane"]:
        return cat_epoch
    return prb_epoch


def _leg_b_baseline_epoch(cycle: int) -> int:
    return _packed_probe_epoch(cycle) - 1


def _run_cycle_one_with_probe(probe_patch: dict) -> tuple[dict, dict]:
    """Run a single replay cycle with a patched probe fixture in an isolated env copy."""
    tmp_root = Path(tempfile.mkdtemp(prefix="blkmir-mixed-"))
    env_copy = tmp_root / "environment"
    shutil.copytree(ENV, env_copy)
    probe_path = env_copy / "fixtures" / "probe_view_a.json"
    probe = json.loads(probe_path.read_text())
    probe.update(probe_patch)
    probe_path.write_text(json.dumps(probe, indent=2) + "\n")
    out_dir = tmp_root / "output"
    out_dir.mkdir()
    _prepare_run_tree(env_copy, out_dir)
    env = _verifier_cycle_env(
        MIRROR_ROOT=str(env_copy),
        OUTPUT_DIR=str(out_dir),
        CYCLE_COUNT="1",
    )
    proc = subprocess.run(VERIFIER_CYCLE, cwd="/app", env=env, check=False)
    assert proc.returncode == 0, proc.stderr
    segments = json.loads((out_dir / "push_trace.json").read_text())["segments"]
    leg_b = next(r for r in segments if r["leg_id"] == "leg-b")
    leg_a = next(r for r in segments if r["leg_id"] == "leg-a")
    return leg_b, leg_a


def _assert_leg_b_quiescent(leg_b: dict, baseline_epoch: int) -> None:
    assert leg_b["hold_ms"] < CONFIG_HOLD_MS
    assert leg_b["epoch"] == baseline_epoch


def _artifact_bundle(root: Path) -> dict:
    return {
        "push": json.loads((root / "push_trace.json").read_text()),
        "digest": json.loads((root / "rolling_digest.json").read_text()),
        "trace": [
            json.loads(x)
            for x in (root / "progress_trace.jsonl").read_text().splitlines()
            if x.strip()
        ],
        "conv": json.loads((root / "convergence_report.json").read_text()),
    }


def test_materialized_lane_split_survives_staging():
    """Lane-routed digest epochs must stay split through coordinator staging when axes remain open."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    catalog = _catalog(1)
    probe = _probe(1)
    side_a = _side_a_view()
    side_b = _side_b_view()
    conv = _load("convergence_report.json")["cycles"][0]
    assert conv["synced_bytes"] > 0
    assert conv["verified_bytes"] == conv["synced_bytes"] or conv["verified_bytes"] < conv["synced_bytes"]
    assert catalog["finished"] is True
    assert probe["hole_debt"] > 0
    assert side_a is not None
    assert side_a["epoch"] == catalog["epoch"]
    assert side_b["epoch"] == probe["epoch"]
    assert side_a["epoch"] != side_b["epoch"]
    assert side_a["tally_hex"] == _tally_hex(side_a["tally"], side_a["epoch"])
    assert side_b["tally_hex"] == _tally_hex(side_b["tally"], side_b["epoch"])


def test_presentation_with_hole_debt_preserves_split_authorities():
    """Finished catalog with hole debt must not seal rank or collapse split digest authorities."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    probe = _probe(1)
    catalog = _catalog(1)
    conv = _load("convergence_report.json")
    cycle1 = conv["cycles"][0]
    side_a = _side_a_view()
    side_b = _side_b_view()
    segments = _load("push_trace.json")
    leg_b = next(r for r in segments if r["leg_id"] == "leg-b")
    assert catalog["finished"] is True
    assert probe["hole_debt"] > 0
    assert probe["holes_cleared"] is False
    assert probe["content_caught"] is False
    assert cycle1["synced_bytes"] > 0
    assert cycle1["verified_bytes"] != cycle1["synced_bytes"]
    assert _max_verified_seal(conv) == 0
    assert side_a is not None
    assert side_a["epoch"] == catalog["epoch"]
    assert side_b["epoch"] == probe["epoch"]
    assert leg_b["epoch"] != cycle1["verified_bytes"]
    if catalog["epoch"] != probe["epoch"]:
        assert side_a["epoch"] != side_b["epoch"]


def test_chunk_wave_does_not_credit_verified_accounting():
    """Chunk wave alone must stage synced bytes without crediting verified accounting."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    conv = _load("convergence_report.json")["cycles"][0]
    trace = _load("progress_trace.jsonl")
    chunk_rows = [row for row in trace if row["epoch"] == 1 and row["op"] == "chunk"]
    assert chunk_rows, "missing chunk wave line"
    assert conv["synced_bytes"] > 0
    assert conv["verified_bytes"] == 0
    assert conv["verified_bytes"] != conv["synced_bytes"]


def test_waves_complete_without_verified_credit_while_axes_open():
    """All three settlement waves may complete while verified accounting stays open on open axes."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    conv = _load("convergence_report.json")["cycles"][0]
    trace = _load("progress_trace.jsonl")
    stage_rows = [row for row in trace if row["epoch"] == 1]
    assert [row["op"] for row in stage_rows] == ["chunk", "roll", "latch"]
    assert conv["synced_bytes"] > 0
    assert conv["verified_bytes"] != conv["synced_bytes"]
    assert _max_verified_seal(_load("convergence_report.json")) == 0
    probe = _probe(1)
    assert probe["hole_debt"] > 0 or not probe["content_caught"]


def test_partial_wave_credit_without_latch_stays_unverified():
    """Hole-axis wave completion without latch must not credit verified byte accounting."""
    tmp_root = Path(tempfile.mkdtemp(prefix="partial-credit-"))
    env_copy = tmp_root / "environment"
    shutil.copytree(ENV, env_copy)
    probe_path = env_copy / "fixtures" / "probe_view_a.json"
    probe = json.loads(probe_path.read_text())
    probe.update(
        {
            "leg_b_io_done": True,
            "hole_clear_mark": True,
            "holes_cleared": True,
            "hole_debt": 0,
            "content_mark": False,
            "content_caught": False,
            "present_mark": True,
        }
    )
    probe_path.write_text(json.dumps(probe, indent=2) + "\n")
    out_dir = tmp_root / "output"
    out_dir.mkdir()
    env = _verifier_cycle_env(
        MIRROR_ROOT=str(env_copy),
        OUTPUT_DIR=str(out_dir),
        CYCLE_COUNT="1",
    )
    proc = subprocess.run(VERIFIER_CYCLE, cwd="/app", env=env, check=False)
    assert proc.returncode == 0, proc.stderr
    conv = json.loads((out_dir / "convergence_report.json").read_text())["cycles"][0]
    assert conv["synced_bytes"] > 0
    assert conv["verified_bytes"] != conv["synced_bytes"]
    segments = json.loads((out_dir / "push_trace.json").read_text())["segments"]
    leg_b = next(r for r in segments if r["leg_id"] == "leg-b")
    _assert_leg_b_quiescent(leg_b, _leg_b_baseline_epoch(1))


def test_destination_leg_triple_gate_matrix():
    """Destination-leg hold and epoch advance only after IO plus both settlement axes close together."""
    roll_only, _ = _run_cycle_one_with_probe(
        {
            "leg_b_io_done": True,
            "hole_clear_mark": True,
            "holes_cleared": True,
            "hole_debt": 0,
            "content_mark": False,
            "content_caught": False,
            "present_mark": True,
        }
    )
    latch_only, _ = _run_cycle_one_with_probe(
        {
            "leg_b_io_done": True,
            "content_mark": True,
            "content_caught": True,
            "hole_clear_mark": False,
            "holes_cleared": False,
            "hole_debt": 2048,
            "present_mark": True,
        }
    )
    full_gate, leg_a = _run_cycle_one_with_probe(
        {
            "leg_b_io_done": True,
            "hole_clear_mark": True,
            "holes_cleared": True,
            "hole_debt": 0,
            "content_mark": True,
            "content_caught": True,
            "present_mark": True,
        }
    )
    baseline = _leg_b_baseline_epoch(1)
    _assert_leg_b_quiescent(roll_only, baseline)
    _assert_leg_b_quiescent(latch_only, baseline)
    assert full_gate["hold_ms"] >= CONFIG_HOLD_MS
    assert full_gate["epoch"] == baseline + 1
    assert full_gate["epoch"] > leg_a["epoch"]


def test_waves_couple_to_progress_trace():
    """Settlement waves must follow chunk, roll, latch trace ordering per cycle."""
    _run_repro({"CYCLE_COUNT": str(DEFAULT_CYCLES)})
    trace = _load("progress_trace.jsonl")
    assert len(trace) >= DEFAULT_CYCLES * 3
    for cycle in range(1, DEFAULT_CYCLES + 1):
        stage_rows = [row for row in trace if row["epoch"] == cycle]
        assert [row["op"] for row in stage_rows] == ["chunk", "roll", "latch"]
        for row in stage_rows:
            assert row["path"] == LOGICAL_PATH


def test_append_resume_rebuilds_from_fixture_not_poison():
    """Append resume must rebuild leg-b epoch floors from fixture authorities and prior latch trace, not partial verified or hole tallies."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    conv_partial = _load("convergence_report.json")["cycles"][0]
    assert conv_partial["verified_bytes"] < conv_partial["synced_bytes"]
    trace_partial = _load("progress_trace.jsonl")
    assert any(row["epoch"] == 1 and row["op"] == "latch" for row in trace_partial)
    probe2 = _probe(2)
    packed_floor = _packed_probe_epoch(2) - 1
    _run_mirctl(OUTPUT, cycle=2, append=True)
    segments = _load("push_trace.json")
    leg_b_rows = [r for r in segments if r["leg_id"] == "leg-b"]
    assert leg_b_rows, "missing leg-b rows after append resume"
    assert all(r["epoch"] != conv_partial["verified_bytes"] for r in leg_b_rows)
    assert all(r["byte_offset"] == probe2["delayed_offset"] for r in leg_b_rows)
    last_leg_b_epoch = leg_b_rows[len(leg_b_rows) - 1]["epoch"]
    assert last_leg_b_epoch >= packed_floor
    assert last_leg_b_epoch >= probe2["epoch"] - 1


def test_dual_authority_digest_survives_hole_debt():
    """Digest views must keep catalog and probe epochs separate while hole debt remains unsettled."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    catalog = _catalog(1)
    probe = _probe(1)
    conv = _load("convergence_report.json")
    side_a = _side_a_view()
    side_b = _side_b_view()
    assert catalog["finished"] is True
    assert probe["hole_debt"] > 0
    assert _max_verified_seal(conv) == 0
    assert probe["epoch"] > catalog["epoch"] or catalog["epoch"] != probe["epoch"]
    assert side_a is not None
    assert side_a["epoch"] == catalog["epoch"]
    assert side_b["epoch"] == probe["epoch"]
    assert side_a["tally"] == catalog["tally"]
    assert side_b["tally"] == probe["tally"]
    assert side_a["tally_hex"] == _tally_hex(side_a["tally"], side_a["epoch"])
    assert side_b["tally_hex"] == _tally_hex(side_b["tally"], side_b["epoch"])


def test_rolling_digest_exports_latest_cycle_pair_only():
    """rolling_digest.json must contain only side-a and side-b views from the latest completed cycle."""
    _run_repro({"CYCLE_COUNT": str(DEFAULT_CYCLES)})
    digest = _load("rolling_digest.json")
    views = digest["views"]
    assert len(views) == 2
    sources = {view["source"] for view in views}
    assert sources == {"side-a", "side-b"}
    catalog = _catalog(DEFAULT_CYCLES)
    probe = _probe(DEFAULT_CYCLES)
    side_a = next(view for view in views if view["source"] == "side-a")
    side_b = next(view for view in views if view["source"] == "side-b")
    assert side_a["epoch"] == catalog["epoch"]
    assert side_a["tally"] == catalog["tally"]
    assert side_b["epoch"] == probe["epoch"]
    assert side_b["tally"] == probe["tally"]


def test_side_b_metric_isolated_from_catalog_blending():
    """Probe-side digest tally must follow probe fixture metrics and stay isolated from catalog blending."""
    _run_repro({"CYCLE_COUNT": str(DEFAULT_CYCLES)})
    probe = _probe(2)
    catalog = _catalog(2)
    side_b = _side_b_view()
    side_a = _side_a_view()
    assert side_b["tally"] == probe["tally"]
    assert side_b["tally"] != catalog["tally"]
    assert side_a is not None
    assert side_a["tally"] == catalog["tally"]
    assert side_b["epoch"] == probe["epoch"]
    assert side_a["epoch"] == catalog["epoch"]
    assert side_b["tally_hex"] == _tally_hex(side_b["tally"], side_b["epoch"])
    digest = _load("rolling_digest.json")
    for view in digest["views"]:
        assert view["tally_hex"] == _tally_hex(view["tally"], view["epoch"])


def test_sealed_append_idempotent_across_rank_boundary():
    """Idempotent mirctl rerun must skip an already-exported settled cycle and leave artifacts unchanged."""
    _run_repro({"CYCLE_COUNT": str(DEFAULT_CYCLES)})
    conv_before = _load("convergence_report.json")
    assert _max_verified_seal(conv_before) == DEFAULT_CYCLES
    before_segments = len(_load("push_trace.json"))
    before_cycles = len(conv_before["cycles"])
    before_trace = _load("progress_trace.jsonl")
    first_digest = _load("rolling_digest.json")
    _run_mirctl(OUTPUT, cycle=DEFAULT_CYCLES, append=True)
    assert len(_load("push_trace.json")) == before_segments
    assert len(_load("convergence_report.json")["cycles"]) == before_cycles
    assert _load("progress_trace.jsonl") == before_trace
    assert _load("rolling_digest.json") == first_digest


def test_delayed_window_settles_after_both_axes():
    """Delayed window sums disagree on cycle one and converge once both settlement axes complete on cycle two."""
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    subprocess.run(
        VERIFIER_CYCLE,
        cwd="/app",
        env=_verifier_cycle_env(OUTPUT_DIR=str(OUTPUT), CYCLE_COUNT="1"),
        check=True,
    )
    probe1 = _probe(1)
    catalog = _catalog(1)
    offset = probe1["delayed_offset"]
    span = probe1["delayed_span"]
    seed_sum = _window_sum(offset, span)
    assert catalog["finished"] is True
    assert probe1["leg_a_sum"] == seed_sum
    assert probe1["leg_b_sum"] != probe1["leg_a_sum"]
    _run_mirctl(OUTPUT, cycle=2, append=True)
    probe2 = _probe(2)
    conv = _load("convergence_report.json")
    final = conv["cycles"][-1]
    assert probe2["leg_a_sum"] == probe2["leg_b_sum"]
    assert probe2["hole_debt"] == 0
    assert probe2["holes_cleared"] is True
    assert probe2["content_caught"] is True
    assert final["verified_bytes"] == final["synced_bytes"]
    assert _max_verified_seal(conv) == 2


def test_cross_artifact_replay_coherence():
    """Full replay coordinates phased waves, dual-axis settlement, trace ordering, leg-b anchors, and digest chain."""
    _run_repro({"CYCLE_COUNT": "2"})
    conv = _load("convergence_report.json")
    assert len(conv["cycles"]) >= 2
    digest = _load("rolling_digest.json")
    segments = _load("push_trace.json")
    trace = _load("progress_trace.jsonl")
    probe = _probe(2)
    for view in digest["views"]:
        assert view["tally_hex"] == _tally_hex(view["tally"], view["epoch"])
    assert len(trace) >= DEFAULT_CYCLES * 3
    for cycle in range(1, DEFAULT_CYCLES + 1):
        stage_rows = [row for row in trace if row["epoch"] == cycle]
        assert [row["op"] for row in stage_rows] == ["chunk", "roll", "latch"]
        for row in stage_rows:
            assert row["path"] == LOGICAL_PATH
        cycle_conv = next(c for c in conv["cycles"] if c["cycle"] == cycle)
        if cycle == 1:
            assert cycle_conv["verified_bytes"] != cycle_conv["synced_bytes"]
            assert cycle_conv["synced_bytes"] > 0
            assert _max_verified_seal({"cycles": conv["cycles"][:1]}) == 0
        else:
            assert cycle_conv["verified_bytes"] == cycle_conv["synced_bytes"]
    leg_b_rows = [r for r in segments if r["leg_id"] == "leg-b"]
    assert all(r["byte_offset"] == probe["delayed_offset"] for r in leg_b_rows)
    side_b = _side_b_view()
    assert side_b["tally"] == probe["tally"]
    leg_a_rows = [r for r in segments if r["leg_id"] == "leg-a"]
    for cycle in range(1, DEFAULT_CYCLES + 1):
        if not _probe(cycle).get("leg_b_io_done", True):
            idx = cycle - 1
            assert leg_b_rows[idx]["epoch"] <= leg_a_rows[idx]["epoch"]


def test_rank_seal_requires_verified_catchup_both_axes():
    """Rank, sealed generation, and digest epochs must stay coupled through dual-axis verified catchup."""
    _run_repro({"CYCLE_COUNT": str(DEFAULT_CYCLES)})
    conv = _load("convergence_report.json")
    cycle1 = next(c for c in conv["cycles"] if c["cycle"] == 1)
    cycle2 = next(c for c in conv["cycles"] if c["cycle"] == 2)
    assert cycle1["verified_bytes"] != cycle1["synced_bytes"]
    assert cycle2["verified_bytes"] == cycle2["synced_bytes"]
    assert _max_verified_seal({"cycles": conv["cycles"][:1]}) == 0
    assert _max_verified_seal(conv) == DEFAULT_CYCLES
    digest = _load("rolling_digest.json")
    catalog = _catalog(DEFAULT_CYCLES)
    probe = _probe(DEFAULT_CYCLES)
    side_a = next(v for v in digest["views"] if v["source"] == "side-a")
    side_b = next(v for v in digest["views"] if v["source"] == "side-b")
    assert side_a["epoch"] == catalog["epoch"]
    assert side_b["epoch"] == probe["epoch"]
    assert probe["hole_debt"] == 0
    assert probe["content_caught"] is True


def test_incremental_append_matches_full_replay():
    """A two-cycle full replay must match cycle-one plus append cycle-two from a clean output directory."""
    tmp_root = Path(tempfile.mkdtemp(prefix="blkmir-equiv-"))
    full_out = tmp_root / "full"
    incr_out = tmp_root / "incr"
    full_out.mkdir()
    incr_out.mkdir()
    subprocess.run(["chown", "-R", VERIFIER_RUN_USER, str(tmp_root)], check=False)
    _prepare_run_tree(ENV, full_out)
    _prepare_run_tree(ENV, incr_out)
    env_full = _verifier_cycle_env(OUTPUT_DIR=str(full_out), CYCLE_COUNT="2")
    assert subprocess.run(VERIFIER_CYCLE, cwd="/app", env=env_full, check=False).returncode == 0
    env_one = _verifier_cycle_env(OUTPUT_DIR=str(incr_out), CYCLE_COUNT="1")
    assert subprocess.run(VERIFIER_CYCLE, cwd="/app", env=env_one, check=False).returncode == 0
    _prepare_run_tree(ENV, incr_out)
    append_env = {
        "MIRROR_ROOT": str(ENV),
        "OUTPUT_DIR": str(incr_out),
        "CYCLE": "2",
        "APPEND_EXPORT": "1",
    }
    mirctl = _mirctl()
    assert mirctl.is_file()
    proc = _run_as([str(mirctl), "run", str(incr_out)], env=append_env, check=False)
    assert proc.returncode == 0, proc.stderr
    full = _artifact_bundle(full_out)
    incr = _artifact_bundle(incr_out)
    assert len(full["push"]["segments"]) == len(incr["push"]["segments"])
    assert full["conv"]["cycles"] == incr["conv"]["cycles"]
    assert full["trace"] == incr["trace"]
    assert full["digest"]["views"] == incr["digest"]["views"]
