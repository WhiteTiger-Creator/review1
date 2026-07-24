import json
import subprocess
import tempfile
from pathlib import Path

import pytest

RUN_BIN = "/app/bin/q7"
TRACE = Path("/app/output/sensitivity_trace.json")
ENV = Path("/app/environment")
FIXTURES = ENV / "fixtures"
ELEM_TOL = 1.0e-10
FINE_BAND = 1.0e-8
LARGE_DT = 0.28
STAB_CAP = 2.0
META_TOL = 1.0e-10
BIND_K = 1.0e-6
BIND_SCALE = 1.0e-10
LINEAGE_K = 0.25
PLACEHOLDER_DIGEST = "deadbeefdeadbeef"

STIFF = "stiff_coupled.json"
SHIFTED = "shifted_stiff.json"
ASYM = "asymmetric_tiles.json"


def _log1p(x: float) -> float:
    result = subprocess.run(
        ["awk", "-v", f"x={x:.17g}", "BEGIN { printf \"%.17g\\n\", log(1+x) }"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return float(result.stdout.strip())


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, **kwargs, check=False)


@pytest.fixture(scope="session", autouse=True)
def build_once():
    result = subprocess.run(
        ["make", "-C", "/app/environment", "all"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert Path("/app/bin/q7").is_file()


def fixture(name: str) -> str:
    return str(FIXTURES / name)


def load_model(path: str) -> dict:
    return json.loads(Path(path).read_text())


def bind_seed_from_digest(digest: str) -> float:
    return int(digest[:8], 16) * BIND_SCALE


def shift_add(bind_seed: float, generation: int) -> float:
    return BIND_K * bind_seed if generation > 0 else 0.0


def tile_lambda(tile: int, spec: dict, extra_shift: float = 0.0) -> float:
    lam = spec["diag"][tile] + spec["shift"] + extra_shift
    if tile > 0:
        lam -= abs(spec["off"][tile - 1])
    if tile + 1 < spec["n"]:
        lam -= abs(spec["off"][tile])
    return lam


def profile_scale(profile_id: int) -> float:
    return 1.0 + 1.0e-7 if profile_id == 1 else 1.0


def v9_elem(tile: int, spec: dict, dt: float, profile_id: int, extra_shift: float = 0.0) -> float:
    lam = tile_lambda(tile, spec, extra_shift)
    denom = 1.0 - dt * lam
    if abs(denom) < 1.0e-18:
        return 0.0
    base = 1.0 / denom
    chain = _log1p(dt * abs(lam) * 0.1)
    return base * (1.0 + chain * profile_scale(profile_id))


def v9_stab(spec: dict, dt: float, extra_shift: float = 0.0) -> float:
    rho = 0.0
    for tile in range(spec["n"]):
        lam = tile_lambda(tile, spec, extra_shift)
        denom = 1.0 - dt * lam
        if abs(denom) < 1.0e-18:
            return 1.0e6
        val = abs(1.0 / denom)
        rho = max(rho, val)
    return rho


def elem_delta(reported: float, reference: float) -> float:
    denom = max(abs(reference), 1.0e-14)
    return abs(reported - reference) / denom


def emit_lane_tag(depth: int, lam_emit: float, bind_seed: float) -> str:
    tag = (depth * 7919 + int(abs(lam_emit) * 1.0e4)) ^ int(bind_seed * 1.0e8)
    return f"{tag & 0xFFFF:04x}"


def clear_trace() -> None:
    TRACE.unlink(missing_ok=True)


def q7run(
    mode: str,
    state_dir: Path,
    model: str | None = None,
    profile: str = "nominal",
    dt: float | None = None,
) -> subprocess.CompletedProcess:
    if mode != "seal":
        clear_trace()
    cmd = [
        RUN_BIN,
        "--mode",
        mode,
        "--state-dir",
        str(state_dir),
        "--trace-out",
        str(TRACE),
    ]
    if mode != "seal":
        assert model is not None
        cmd.extend(["--model", model, "--profile", profile])
    if dt is not None:
        cmd.extend(["--dt", str(dt)])
    return _run(cmd)


def load_trace() -> dict:
    return json.loads(TRACE.read_text())


def policy_digest(rows: list) -> str:
    ordered = sorted(rows, key=lambda r: r["tile_id"])
    parts = []
    for row in ordered:
        parts.append(
            '{{"tile_id":"{}","reported":{:.17g},"reference":{:.17g},"profile":"{}","emit_lane":"{}"}}'.format(
                row["tile_id"],
                row["reported"],
                row["reference"],
                row["profile"],
                row["emit_lane"],
            )
        )
    body = '{"rows":[' + ",".join(parts) + "]}"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
        handle.write(body)
        body_path = handle.name
    result = subprocess.run(
        ["sha256sum", body_path],
        capture_output=True,
        text=True,
        check=True,
    )
    Path(body_path).unlink(missing_ok=True)
    return result.stdout.split()[0][:16]


def read_generation(state_dir: Path) -> int:
    head = json.loads((state_dir / "head.json").read_text())
    return int(head["generation"])


def sealed_slots(state_dir: Path) -> list[dict]:
    slots = []
    for idx in range(2):
        path = state_dir / f"slot_{idx}.json"
        if not path.exists():
            continue
        slot = json.loads(path.read_text())
        if slot.get("sealed") and slot.get("digest"):
            slots.append(slot)
    return slots


def newest_sealed_slot(state_dir: Path) -> dict:
    slots = sealed_slots(state_dir)
    assert slots
    return max(slots, key=lambda slot: int(slot.get("slot_generation", 0)))


def workflow_start_seal(state_dir: Path, model: str, profile: str = "nominal") -> dict:
    assert q7run("start", state_dir, model, profile=profile).returncode == 0
    trace = load_trace()
    assert q7run("seal", state_dir).returncode == 0
    return trace


def assert_elem_rows(
    model_name: str,
    state_dir: Path,
    profile: str = "nominal",
    dt: float | None = None,
    mode: str = "start",
    generation: int = 0,
    bind_seed: float = 0.0,
) -> dict:
    """Run q7 and verify every row meets the element band.

    Rebuilds the reference v9_elem for each tile at the active dt/profile and
    asserts elem_delta <= ELEM_TOL for both reported and reference. Returns the
    loaded trace dict.
    """
    model = fixture(model_name)
    spec = load_model(model)
    profile_id = 1 if profile == "scaled" else 0
    use_dt = spec["dt_step"] if dt is None else dt
    extra = shift_add(bind_seed, generation)
    result = q7run(mode, state_dir, model, profile=profile, dt=dt)
    assert result.returncode == 0, result.stderr
    trace = load_trace()
    assert len(trace["rows"]) == spec["n"]
    for row in trace["rows"]:
        tile = int(row["tile_id"])
        expected = v9_elem(tile, spec, use_dt, profile_id, extra)
        assert elem_delta(row["reported"], expected) <= ELEM_TOL
        assert elem_delta(row["reference"], expected) <= ELEM_TOL
        assert row["profile"] == profile
        depth = tile + 1
        lam_emit = tile_lambda(tile, spec, extra)
        assert row["emit_lane"] == emit_lane_tag(depth, lam_emit, bind_seed)
    return trace


def test_xr01_start_shape():
    """Start segment trace exposes rows, emit_lane tags, profile labels, and repro_digest."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    result = q7run("start", state, fixture(STIFF))
    assert result.returncode == 0, result.stderr
    trace = load_trace()
    assert isinstance(trace["rows"], list) and trace["rows"]
    row = trace["rows"][0]
    for key in ("tile_id", "reported", "reference", "profile", "emit_lane"):
        assert key in row
    digest = trace["repro_digest"]
    assert isinstance(digest, str) and len(digest) == 16
    assert digest == digest.lower()
    assert digest == policy_digest(trace["rows"])


def test_xr02_start_elem_nominal():
    """Generation-zero start on nominal satisfies the element band."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    assert_elem_rows(STIFF, state, profile="nominal", mode="start", generation=0, bind_seed=0.0)


def test_xr03_seal_bumps_generation():
    """Seal increments generation and records bind_seed from the digest."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    trace = workflow_start_seal(state, fixture(STIFF))
    assert read_generation(state) == 1
    slot0 = json.loads((state / "slot_0.json").read_text())
    assert slot0["sealed"] == 1
    assert slot0["bind_seed"] > 0.0
    assert slot0["slot_generation"] == 1
    assert abs(slot0["lineage_seed"] - slot0["bind_seed"]) <= 1e-20
    assert trace["repro_digest"] == policy_digest(trace["rows"])


def test_xr04_resume_scaled_delayed_elem():
    """Resumed scaled segment with bind_seed must meet the element band."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    start_trace = workflow_start_seal(state, fixture(STIFF))
    bind_seed = bind_seed_from_digest(start_trace["repro_digest"])
    generation = read_generation(state)
    assert bind_seed > 0.0
    assert_elem_rows(
        STIFF,
        state,
        profile="scaled",
        mode="resume",
        generation=generation,
        bind_seed=bind_seed,
    )


def test_xr05_checkpoint_idempotent():
    """Repeated resume reruns emit identical reproducibility digests."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    workflow_start_seal(state, fixture(STIFF))
    assert q7run("resume", state, fixture(STIFF), profile="scaled").returncode == 0
    first = load_trace()["repro_digest"]
    assert q7run("resume", state, fixture(STIFF), profile="scaled").returncode == 0
    second = load_trace()["repro_digest"]
    assert first == second
    assert first == policy_digest(load_trace()["rows"])


def test_xr06_resume_requires_seal():
    """Resume without a sealed slot returns exit code 64."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    assert q7run("start", state, fixture(STIFF)).returncode == 0
    result = q7run("resume", state, fixture(STIFF), profile="scaled")
    assert result.returncode == 64


def test_xr07_torn_slot_recovery():
    """Truncated active slot must recover bind_seed from the alternate sealed slot."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    start_trace = workflow_start_seal(state, fixture(STIFF))
    bind_seed = bind_seed_from_digest(start_trace["repro_digest"])
    head = json.loads((state / "head.json").read_text())
    active = int(head["active_slot"])
    slot_path = state / f"slot_{active}.json"
    slot_path.write_text('{"sealed":0,"digest":"",')
    generation = read_generation(state)
    assert_elem_rows(
        STIFF,
        state,
        profile="scaled",
        mode="resume",
        generation=generation,
        bind_seed=bind_seed,
    )


def test_xr08_fine_probe_resumed():
    """Fine probe class agreement after resumed scaled segment."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    start_trace = workflow_start_seal(state, fixture(STIFF))
    bind_seed = bind_seed_from_digest(start_trace["repro_digest"])
    generation = read_generation(state)
    extra = shift_add(bind_seed, generation)
    spec = load_model(fixture(STIFF))
    model = fixture(STIFF)
    assert q7run("resume", state, model, profile="scaled").returncode == 0
    for dt in spec["dt_fine"]:
        for tile in range(spec["n"]):
            h = dt * 0.25
            rep0 = reported_at(state, model, tile, dt, "scaled", "resume", bind_seed, generation)
            rep1 = reported_at(state, model, tile, dt + h, "scaled", "resume", bind_seed, generation)
            pipeline = (rep1 - rep0) / h if h > 0 else 0.0
            f0 = v9_elem(tile, spec, dt, 1, extra)
            f1 = v9_elem(tile, spec, dt + h, 1, extra)
            probe = (f1 - f0) / h if h > 0 else 0.0
            assert abs(pipeline - probe) <= FINE_BAND


def reported_at(
    state_dir: Path,
    model: str,
    tile: int,
    dt: float,
    profile: str,
    mode: str,
    bind_seed: float,
    generation: int,
) -> float:
    result = q7run(mode, state_dir, model, profile=profile, dt=dt)
    assert result.returncode == 0, result.stderr
    for row in load_trace()["rows"]:
        if int(row["tile_id"]) == tile:
            return float(row["reported"])
    raise AssertionError(f"tile {tile} missing from trace")


def test_xr09_large_step_resumed():
    """Large-step reported rows stay inside the element band after resume."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    start_trace = workflow_start_seal(state, fixture(STIFF))
    bind_seed = bind_seed_from_digest(start_trace["repro_digest"])
    generation = read_generation(state)
    spec = load_model(fixture(STIFF))
    assert spec["dt_large"] >= LARGE_DT
    extra = shift_add(bind_seed, generation)
    assert v9_stab(spec, spec["dt_large"], extra) <= STAB_CAP
    assert_elem_rows(
        STIFF,
        state,
        profile="scaled",
        dt=spec["dt_large"],
        mode="resume",
        generation=generation,
        bind_seed=bind_seed,
    )


def test_xr10_asymmetric_resumed():
    """Asymmetric fixture satisfies element band on resumed scaled segment."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    start_trace = workflow_start_seal(state, fixture(ASYM))
    bind_seed = bind_seed_from_digest(start_trace["repro_digest"])
    generation = read_generation(state)
    assert_elem_rows(
        ASYM,
        state,
        profile="scaled",
        mode="resume",
        generation=generation,
        bind_seed=bind_seed,
    )


def test_xr11_metamorphic_shift_resumed():
    """Shifted stiff metamorphic baseline remains stable after resume."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    workflow_start_seal(state, fixture(STIFF))
    generation = read_generation(state)
    sealed = newest_sealed_slot(state)
    bind_seed = sealed["bind_seed"]
    base_spec = load_model(fixture(STIFF))
    shift_spec = load_model(fixture(SHIFTED))
    base_trace = assert_elem_rows(
        STIFF,
        state,
        mode="resume",
        profile="scaled",
        generation=generation,
        bind_seed=bind_seed,
    )
    state2 = Path(tempfile.mkdtemp(prefix="q7_state_"))
    workflow_start_seal(state2, fixture(STIFF))
    generation2 = read_generation(state2)
    sealed2 = newest_sealed_slot(state2)
    bind_seed2 = sealed2["bind_seed"]
    shift_trace = assert_elem_rows(
        SHIFTED,
        state2,
        mode="resume",
        profile="scaled",
        generation=generation2,
        bind_seed=bind_seed2,
    )
    base_rows = sorted(base_trace["rows"], key=lambda r: r["tile_id"])
    shift_rows = sorted(shift_trace["rows"], key=lambda r: r["tile_id"])
    assert [r["tile_id"] for r in base_rows] == [r["tile_id"] for r in shift_rows]
    dt = base_spec["dt_step"]
    extra = shift_add(bind_seed2, generation2)
    shift_deltas = []
    for base_row, shift_row in zip(base_rows, shift_rows):
        tile = int(base_row["tile_id"])
        base_ref = v9_elem(tile, base_spec, dt, 1, extra)
        shift_ref = v9_elem(tile, shift_spec, dt, 1, extra)
        shift_deltas.append(elem_delta(base_ref, shift_ref))
    assert abs(shift_spec["shift"]) > META_TOL
    assert max(shift_deltas) > META_TOL


def test_xr12_touch_guard_resumed():
    """Touching trace output then rerunning resume regenerates driver-backed content."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    workflow_start_seal(state, fixture(STIFF))
    assert q7run("resume", state, fixture(STIFF), profile="scaled").returncode == 0
    TRACE.write_text(json.dumps({"rows": [], "repro_digest": PLACEHOLDER_DIGEST}))
    generation = read_generation(state)
    sealed = newest_sealed_slot(state)
    bind_seed = sealed["bind_seed"]
    assert q7run("resume", state, fixture(STIFF), profile="scaled").returncode == 0
    regen = load_trace()
    assert regen["repro_digest"] != PLACEHOLDER_DIGEST
    assert_elem_rows(
        STIFF,
        state,
        profile="scaled",
        mode="resume",
        generation=generation,
        bind_seed=bind_seed,
    )


def test_xr13_second_seal_lineage_seed():
    """Second-generation resume uses newest sealed lineage_seed, not the old slot."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    first_trace = workflow_start_seal(state, fixture(STIFF))
    first_seed = bind_seed_from_digest(first_trace["repro_digest"])
    assert q7run("resume", state, fixture(STIFF), profile="scaled").returncode == 0
    resumed_digest = load_trace()["repro_digest"]
    second_seed = bind_seed_from_digest(resumed_digest)
    assert q7run("seal", state).returncode == 0
    generation = read_generation(state)
    assert generation == 2
    newest = newest_sealed_slot(state)
    expected_lineage = second_seed + LINEAGE_K * first_seed
    assert newest["slot_generation"] == 2
    assert abs(newest["lineage_seed"] - expected_lineage) <= 1e-20
    assert_elem_rows(
        STIFF,
        state,
        profile="scaled",
        mode="resume",
        generation=generation,
        bind_seed=expected_lineage,
    )


def test_xr14_second_generation_torn_old_slot():
    """Corrupting the older sealed slot must not mask the newest lineage slot."""
    state = Path(tempfile.mkdtemp(prefix="q7_state_"))
    first_trace = workflow_start_seal(state, fixture(STIFF))
    first_seed = bind_seed_from_digest(first_trace["repro_digest"])
    assert q7run("resume", state, fixture(STIFF), profile="scaled").returncode == 0
    second_seed = bind_seed_from_digest(load_trace()["repro_digest"])
    assert q7run("seal", state).returncode == 0
    slots = sealed_slots(state)
    old = min(slots, key=lambda slot: int(slot["slot_generation"]))
    for idx in range(2):
        slot_path = state / f"slot_{idx}.json"
        slot = json.loads(slot_path.read_text())
        if slot.get("digest") == old["digest"]:
            slot_path.write_text('{"sealed":1,"digest":"",')
            break
    expected_lineage = second_seed + LINEAGE_K * first_seed
    assert_elem_rows(
        ASYM,
        state,
        profile="scaled",
        mode="resume",
        generation=2,
        bind_seed=expected_lineage,
    )
