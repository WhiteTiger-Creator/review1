import hashlib
import json
import os
import shutil
import subprocess
import pytest

BIN = "/app/bin/fyop-atlas"
STATE = "/app/state"
OUTPUT = "/app/output"
YARD = "/app/yard-alpha"
FIXTURES = "/opt/verifier-fixtures/hfsy"
# Opaque hidden observation dirs (verify-only; never in agent image)
TB3_OBS_K4M1 = os.environ.get("TB3_OBS_K4M1", os.path.join(FIXTURES, "obs-k4m1"))
TB3_OBS_P9W2 = os.environ.get("TB3_OBS_P9W2", os.path.join(FIXTURES, "obs-p9w2"))
TB3_OBS_R7N3 = os.environ.get("TB3_OBS_R7N3", os.path.join(FIXTURES, "obs-r7n3"))


def _run(cmd, env_override=None):
    """Run fyop-atlas via subprocess."""
    merged = dict(os.environ)
    if env_override:
        merged.update(env_override)
    return subprocess.run(
        [BIN] + cmd,
        capture_output=True, text=True, env=merged, timeout=120,
    )


def _clean():
    for d in (STATE, OUTPUT):
        if os.path.isdir(d):
            shutil.rmtree(d)


def _full_pipeline(env=None):
    _clean()
    r1 = _run(["ingest"], env)
    assert r1.returncode == 0, f"ingest failed: {r1.stderr}"
    r2 = _run(["optimize"], env)
    assert r2.returncode == 0, f"optimize failed: {r2.stderr}"
    r3 = _run(["export"], env)
    assert r3.returncode == 0, f"export failed: {r3.stderr}"


def _load(path):
    with open(path) as f:
        return json.load(f)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reference_staging_hash(yard_dir):
    """Independent reference: compute correct staging_hash from raw inputs."""
    topo = json.loads(open(os.path.join(yard_dir, "topology.json")).read())
    consist = json.loads(open(os.path.join(yard_dir, "consist.json")).read())
    plan = json.loads(open(os.path.join(yard_dir, "plan.json")).read())
    fail_path = os.path.join(yard_dir, "failures.json")
    fail = json.loads(open(fail_path).read()) if os.path.exists(fail_path) else {}
    body = {
        "train_id": consist["train_id"],
        "topology": topo,
        "consist": consist["cars"],
        "plan": plan,
        "failures": fail,
    }
    return _sha256(_canonical(body))


def _reference_topo(yard_dir):
    return json.loads(open(os.path.join(yard_dir, "topology.json")).read())


def _edge_length_lookup(topo):
    """Undirected (from,to) -> length_m from topology switches."""
    edges = {}
    for s in topo["switches"]:
        edges[(s["from_track"], s["to_track"])] = float(s["length_m"])
        edges[(s["to_track"], s["from_track"])] = float(s["length_m"])
    return edges


def _reference_total_distance_m(seq, topo):
    """Independent recomputation: sum length_m for each PUSH/PULL/MOVE_LOCO."""
    edges = _edge_length_lookup(topo)
    total = 0.0
    for cmd in seq["commands"]:
        if cmd["type"] not in ("PUSH", "PULL", "MOVE_LOCO"):
            continue
        key = (cmd["from_track"], cmd["to_track"])
        assert key in edges, f"no topology edge for move {cmd['from_track']}->{cmd['to_track']}"
        total += edges[key]
    return total


def _can_reach_lead(topo, failed_switches, start_track):
    """BFS reachability from start_track to LEAD excluding failed switch ids."""
    if start_track == "LEAD":
        return True
    failed = set(failed_switches or [])
    adj = {}
    for s in topo["switches"]:
        if s["id"] in failed:
            continue
        adj.setdefault(s["from_track"], []).append(s["to_track"])
        adj.setdefault(s["to_track"], []).append(s["from_track"])
    seen = {start_track}
    queue = [start_track]
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, []):
            if nxt in seen:
                continue
            if nxt == "LEAD":
                return True
            seen.add(nxt)
            queue.append(nxt)
    return False


def _independent_capacity_ok(seq, topo, consist):
    """Replay PUSH/PULL and verify dual occupancy inequalities."""
    track_limits = {t["id"]: t for t in topo["tracks"]}
    car_map = {c["id"]: c for c in consist["cars"]}
    track_cars = {t["id"]: [] for t in topo["tracks"]}
    track_cars["LEAD"] = [c["id"] for c in consist["cars"]]
    for cmd in seq["commands"]:
        if cmd["type"] not in ("PUSH", "PULL"):
            continue
        fr = cmd["from_track"]
        to = cmd["to_track"]
        for cid in cmd.get("car_ids", []):
            if cid in track_cars.get(fr, []):
                track_cars[fr].remove(cid)
            track_cars.setdefault(to, []).append(cid)
        if to not in track_limits:
            continue
        lim = track_limits[to]
        on_track = track_cars[to]
        if len(on_track) > lim["max_cars"]:
            return False
        total_len = sum(car_map[c]["length_units"] for c in on_track if c in car_map)
        if total_len > lim["max_length_units"]:
            return False
    return True


def _assert_no_failed_throws(seq, failed):
    failed = set(failed or [])
    for cmd in seq["commands"]:
        if cmd["type"] == "THROW_SWITCH":
            assert cmd["switch_id"] not in failed, (
                f"THROW_SWITCH on failed switch {cmd['switch_id']}"
            )


# ── 1. Build succeeds ──────────────────────────────────────────────────
def test_build_binary_exists():
    """fyop-atlas launcher must exist after build."""
    assert os.path.isfile(BIN), f"{BIN} missing after build"


# ── 2. Ingest creates staging and snapshot ─────────────────────────────
def test_ingest_creates_staging_files():
    """Ingest must produce /app/state/yard-staging.json and /app/state/ingest-snapshot.json."""
    _clean()
    r = _run(["ingest"])
    assert r.returncode == 0
    assert os.path.isfile("/app/state/yard-staging.json")
    assert os.path.isfile("/app/state/ingest-snapshot.json")


# ── 3. Staging schema has required keys ────────────────────────────────
def test_staging_schema():
    """yard-staging.json must contain train_id, topology, consist, plan, failures, staging_hash."""
    _clean()
    _run(["ingest"])
    staging = _load("/app/state/yard-staging.json")
    for key in ("train_id", "topology", "consist", "plan", "failures", "staging_hash"):
        assert key in staging, f"staging missing key: {key}"


# ── 4. Staging hash uses canonical sorted-key JSON ─────────────────────
def test_staging_hash_canonical():
    """staging_hash must equal SHA-256 of canonical compact JSON with sorted keys."""
    _clean()
    _run(["ingest"])
    staging = _load(os.path.join(STATE, "yard-staging.json"))
    ref_hash = _reference_staging_hash(YARD)
    assert staging["staging_hash"] == ref_hash, (
        f"staging_hash mismatch: got {staging['staging_hash']}, expected {ref_hash}"
    )


# ── 5. Ingest snapshot has correct car count ───────────────────────────
def test_snapshot_car_count():
    """ingest-snapshot.json car_count must match consist length."""
    _clean()
    _run(["ingest"])
    snap = _load(os.path.join(STATE, "ingest-snapshot.json"))
    consist = json.loads(open(os.path.join(YARD, "consist.json")).read())
    assert snap["car_count"] == len(consist["cars"])


# ── 6. Validate produces validated output ──────────────────────────────
def test_validate_creates_validated():
    """Validate must produce /app/state/shunting-validated.json."""
    _full_pipeline()
    assert os.path.isfile("/app/state/shunting-validated.json")
    validated = _load("/app/state/shunting-validated.json")
    assert "commands" in validated and "validation_seal" in validated


# ── 7. Export produces sequence output ─────────────────────────────────
def test_export_creates_output():
    """Export must produce /app/output/shunting-sequence.json, /app/state/export-manifest.json, /app/state/export-ledger.json."""
    _full_pipeline()
    assert os.path.isfile("/app/output/shunting-sequence.json")
    assert os.path.isfile("/app/state/export-manifest.json")
    assert os.path.isfile("/app/state/export-ledger.json")
    seq = _load("/app/output/shunting-sequence.json")
    assert "commands" in seq and "total_distance_m" in seq
    manifest = _load("/app/state/export-manifest.json")
    assert "export_fingerprint" in manifest
    ledger = _load("/app/state/export-ledger.json")
    assert "exports" in ledger and len(ledger["exports"]) >= 1


# ── 8. Distance metric uses meters, not hop count ─────────────────────
def test_distance_is_meters_not_hops():
    """total_distance_m must match independent length_m sum for this sequence.

    Graded contract is geometric accounting on the emitted commands only.
    This is not a check for globally shortest distance or minimal move count.
    """
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    dist = float(seq["total_distance_m"])
    topo = _reference_topo(YARD)
    ref = _reference_total_distance_m(seq, topo)
    assert abs(dist - ref) < 1e-6, (
        f"total_distance_m={dist} != independent length_m sum {ref} "
        f"(accounting mismatch; not an optimality check)"
    )
    move_count = sum(
        1 for c in seq["commands"] if c["type"] in ("PUSH", "PULL", "MOVE_LOCO")
    )
    assert dist != float(move_count), (
        "total_distance_m equals hop count — must use edge.length_m accounting"
    )
    min_edge = min(s["length_m"] for s in topo["switches"])
    assert dist >= min_edge, (
        f"total_distance_m={dist} is smaller than min edge length_m={min_edge}"
    )


# ── 9. Destination blocks follow plan order ────────────────────────────
def test_outbound_blocks_plan_order():
    """Within each outbound track, blocks must follow destination_order from plan.json."""
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    plan = json.loads(open(os.path.join(YARD, "plan.json")).read())
    dest_order = plan["destination_order"]
    for track_id, blocks in seq["outbound_blocks"].items():
        dests_on_track = [b["destination"] for b in blocks]
        order_indices = [dest_order.index(d) for d in dests_on_track if d in dest_order]
        assert order_indices == sorted(order_indices), (
            f"blocks on {track_id} not in destination_order: {dests_on_track}"
        )


# ── 10. Capacity never exceeded during sequence ───────────────────────
def test_capacity_never_exceeded():
    """Simulate the command sequence and verify dual occupancy inequalities."""
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    validated = _load(os.path.join(STATE, "shunting-validated.json"))
    topo = _reference_topo(YARD)
    consist = json.loads(open(os.path.join(YARD, "consist.json")).read())
    assert _independent_capacity_ok(seq, topo, consist), (
        "emitted sequence violates n_cars or length_units capacity inequalities"
    )
    assert validated.get("capacity_verified") is True, (
        "capacity_verified must be true when the dual inequalities hold"
    )


# ── 11. No THROW_SWITCH on a failed switch ────────────────────────────
def test_no_throw_on_failed_switch():
    """Sequence must never THROW_SWITCH a switch listed in failures.json."""
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    fail = json.loads(open(os.path.join(YARD, "failures.json")).read())
    _assert_no_failed_throws(seq, fail.get("failed_switches", []))


# ── 12. Export fingerprint is stable on re-export ─────────────────────
def test_export_fingerprint_stable():
    """Re-running export on unchanged validated data must yield same fingerprint."""
    _full_pipeline()
    m1 = _load(os.path.join(STATE, "export-manifest.json"))
    fp1 = m1["export_fingerprint"]
    _run(["export"])
    m2 = _load(os.path.join(STATE, "export-manifest.json"))
    fp2 = m2["export_fingerprint"]
    assert fp1 == fp2, f"fingerprint changed: {fp1} -> {fp2}"


# ── 13. Staging hash stable on re-ingest ──────────────────────────────
def test_staging_hash_stable_re_ingest():
    """Re-running ingest with same inputs must produce same staging_hash."""
    _clean()
    _run(["ingest"])
    s1 = _load(os.path.join(STATE, "yard-staging.json"))
    h1 = s1["staging_hash"]
    _run(["ingest"])
    s2 = _load(os.path.join(STATE, "yard-staging.json"))
    h2 = s2["staging_hash"]
    assert h1 == h2, f"staging_hash changed on re-ingest: {h1} -> {h2}"


# ── 14. HFSY_YARD_DIR override works for full pipeline ────────────────
def test_hfsy_yard_dir_override():
    """Pipeline with HFSY_YARD_DIR pointing to a hidden observation set must succeed."""
    obs_dir = TB3_OBS_K4M1
    if not os.path.isdir(obs_dir):
        pytest.skip("obs-k4m1 fixture not found")
    _full_pipeline(env={"HFSY_YARD_DIR": obs_dir})
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    assert seq["train_id"] == "HEAVY-REAR-9901"


# ── 15. Hidden obs-k4m1: dual capacity inequalities under tight outbound ─
def test_hidden_obs_k4m1_capacity():
    """obs-k4m1 shares O1 across A+B so length_units pressure exceeds car-count pressure."""
    obs_dir = TB3_OBS_K4M1
    if not os.path.isdir(obs_dir):
        pytest.skip("obs-k4m1 fixture not found")
    _full_pipeline(env={"HFSY_YARD_DIR": obs_dir})
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    validated = _load(os.path.join(STATE, "shunting-validated.json"))
    topo = json.loads(open(os.path.join(obs_dir, "topology.json")).read())
    consist = json.loads(open(os.path.join(obs_dir, "consist.json")).read())
    independent = _independent_capacity_ok(seq, topo, consist)
    assert independent, (
        "obs-k4m1 sequence violates max_cars or max_length_units"
    )
    # Never claim capacity_verified when the emitted sequence already breaches inequalities.
    if validated.get("capacity_verified") is True:
        assert independent


# ── 16. Hidden obs-p9w2: failed switch lies on the short C2→O1 path ───
def test_hidden_obs_p9w2_no_failed_throw():
    """obs-p9w2 fails SW5 while destination B must leave C2 toward O1."""
    obs_dir = TB3_OBS_P9W2
    if not os.path.isdir(obs_dir):
        pytest.skip("obs-p9w2 fixture not found")
    _full_pipeline(env={"HFSY_YARD_DIR": obs_dir})
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    validated = _load(os.path.join(STATE, "shunting-validated.json"))
    fail = json.loads(open(os.path.join(obs_dir, "failures.json")).read())
    failed = set(fail.get("failed_switches", []))
    assert "SW5" in failed
    _assert_no_failed_throws(seq, failed)
    assert validated.get("capacity_verified") is True


# ── 17. Hidden obs-r7n3: closure is residual reachability, not end-on-LEAD ─
def test_hidden_obs_r7n3_closure_reachability():
    """obs-r7n3 leaves loco off LEAD; closure_verified requires residual BFS, not equality."""
    obs_dir = TB3_OBS_R7N3
    if not os.path.isdir(obs_dir):
        pytest.skip("obs-r7n3 fixture not found")
    _full_pipeline(env={"HFSY_YARD_DIR": obs_dir})
    validated = _load(os.path.join(STATE, "shunting-validated.json"))
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    topo = json.loads(open(os.path.join(obs_dir, "topology.json")).read())
    fail = json.loads(open(os.path.join(obs_dir, "failures.json")).read())
    loco = seq["loco_end_track"]
    assert loco != "LEAD", (
        "obs-r7n3 must leave loco_end_track off LEAD so reachability (not equality) is graded"
    )
    assert validated.get("closure_verified") is True, "closure_verified must be true"
    assert _can_reach_lead(topo, fail.get("failed_switches", []), loco), (
        f"loco_end_track={loco} has no non-failed path to LEAD "
        f"(reachability required; ending on LEAD is not required)"
    )


# ── 18. Full pipeline emits a non-empty command list ──────────────────
def test_pipeline_emits_commands():
    """End-to-end ingest/validate/export must emit at least one shunting command."""
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    assert "commands" in seq
    assert len(seq["commands"]) > 0


# ── 19. NOP: missing staging means validate and export fail ───────────
def test_nop_no_staging_fails():
    """Without ingest, validate must fail (no staging file)."""
    _clean()
    r = _run(["optimize"])
    assert r.returncode != 0 or not os.path.isfile(
        os.path.join(STATE, "shunting-validated.json")
    )


# ── 20. Export reads from validated, not raw yard ─────────────────────
def test_export_reads_validated_not_raw():
    """Export output must match validated data, not re-derive from raw yard."""
    _full_pipeline()
    validated = _load(os.path.join(STATE, "shunting-validated.json"))
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    assert seq["total_distance_m"] == validated["total_distance_m"]
    assert seq["loco_end_track"] == validated["loco_end_track"]
    assert seq["train_id"] == validated["train_id"]


# ── 21. Loco closure: able to reach LEAD (not required to end on LEAD) ─
def test_loco_closure_can_reach_lead():
    """Closure requires a non-failed path from loco_end_track to LEAD.

    Docs and grading agree: LEAD is a reachability target, not a required end track.
    loco_end_track may differ from LEAD when a path still exists.
    """
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    validated = _load(os.path.join(STATE, "shunting-validated.json"))
    topo = _reference_topo(YARD)
    fail = json.loads(open(os.path.join(YARD, "failures.json")).read())
    loco = seq["loco_end_track"]
    assert validated.get("closure_verified") is True, "closure_verified must be true"
    assert _can_reach_lead(topo, fail.get("failed_switches", []), loco), (
        f"loco_end_track={loco} has no non-failed path to LEAD"
    )
    # Fairness: ending on LEAD is sufficient but not required by the contract.
    assert "loco_end_track" in seq


# ── 22. Cars preserve relative inbound order within destination block ─
def test_cars_stable_sort_within_block():
    """Within each destination block, car order must match inbound consist order."""
    _full_pipeline()
    seq = _load(os.path.join(OUTPUT, "shunting-sequence.json"))
    consist = json.loads(open(os.path.join(YARD, "consist.json")).read())
    inbound_order = [c["id"] for c in consist["cars"]]
    for track_id, blocks in seq["outbound_blocks"].items():
        for block in blocks:
            car_ids = block["car_ids"]
            indices = [inbound_order.index(cid) for cid in car_ids]
            assert indices == sorted(indices), (
                f"cars in block {block['destination']} on {track_id} not in consist order"
            )


# ── 23. Cross-run export-ledger accumulates entries ───────────────────
def test_cross_run_ledger():
    """Running full pipeline twice should create two ledger entries."""
    _full_pipeline()
    _run(["export"])
    ledger = _load(os.path.join(STATE, "export-ledger.json"))
    assert len(ledger["exports"]) >= 2


# ── 24. Agent staging_hash for hidden observation differs from default ─
def test_hidden_fixture_staging_hash_differs():
    """Agent fyop-atlas ingest must seal distinct staging_hash for obs-k4m1 vs yard-alpha."""
    assert os.path.isfile(BIN), f"missing agent binary: {BIN}"
    obs_dir = TB3_OBS_K4M1
    if not os.path.isdir(obs_dir):
        pytest.skip("obs-k4m1 fixture not found")

    _clean()
    r_alpha = _run(["ingest"])
    assert r_alpha.returncode == 0, f"default ingest failed: {r_alpha.stderr}"
    staging_alpha = os.path.join(STATE, "yard-staging.json")
    assert os.path.isfile(staging_alpha), "agent did not write yard-staging.json for yard-alpha"
    hash_alpha = _load(staging_alpha)["staging_hash"]
    assert isinstance(hash_alpha, str) and len(hash_alpha) == 64

    _clean()
    r_obs = _run(["ingest"], env_override={"HFSY_YARD_DIR": obs_dir})
    assert r_obs.returncode == 0, f"hidden ingest failed: {r_obs.stderr}"
    staging_obs = os.path.join(STATE, "yard-staging.json")
    assert os.path.isfile(staging_obs), "agent did not write yard-staging.json for hidden obs"
    hash_obs = _load(staging_obs)["staging_hash"]
    assert isinstance(hash_obs, str) and len(hash_obs) == 64

    assert hash_alpha != hash_obs
    assert hash_alpha == _reference_staging_hash(YARD)
    assert hash_obs == _reference_staging_hash(obs_dir)


# ── 25. OccupancyGuard must enforce max_length_units, not car-count alone ─
def test_occupancy_guard_enforces_length_units():
    """Direct contract: can_push rejects length overflow even when max_cars still has slack."""
    from fyop.consist.cars import FreightCar
    from fyop.occupancy.guard import OccupancyGuard, TrackState
    from fyop.topology.graph import TrackNode

    track = TrackNode(id="T1", type="classification", max_cars=4, max_length_units=20)
    state = TrackState("T1")
    state.add_car(FreightCar(id="A", destination="X", length_units=12, mass_t=10.0))
    incoming = FreightCar(id="B", destination="X", length_units=10, mass_t=10.0)
    # car-count allows (2 <= 4) but length 22 > 20
    assert OccupancyGuard.can_push(track, state, incoming) is False


# ── 26. Residual reachability is BFS, not loco_end_track == LEAD ───────
def test_reachability_helper_is_bfs_not_equality():
    """Direct contract: loco off LEAD with a residual path must still close."""
    from fyop.residual.reach import can_loco_reach_lead
    from fyop.topology.graph import SwitchEdge, TrackNode, YardGraph

    tracks = {
        "LEAD": TrackNode(id="LEAD", type="lead", max_cars=10, max_length_units=100),
        "C1": TrackNode(id="C1", type="classification", max_cars=4, max_length_units=40),
        "DEAD": TrackNode(id="DEAD", type="classification", max_cars=2, max_length_units=20),
    }
    edges = [
        SwitchEdge(id="SW1", from_track="LEAD", to_track="C1", length_m=100.0),
        SwitchEdge(id="SWX", from_track="LEAD", to_track="DEAD", length_m=50.0),
    ]
    graph = YardGraph(tracks, edges)
    assert can_loco_reach_lead(graph, "C1", set()) is True
    assert can_loco_reach_lead(graph, "DEAD", {"SWX"}) is False
    assert can_loco_reach_lead(graph, "LEAD", set()) is True


# ── 27. Optimize capacity replay must enforce length_units ─────────────
def test_optimize_simulate_capacity_enforces_length():
    """Direct contract: optimize-stage replay rejects length overflow with car-count slack."""
    from fyop.consist.cars import FreightCar
    from fyop.residual.physics_gate import _simulate_capacity
    from fyop.topology.graph import SwitchEdge, TrackNode, YardGraph
    from fyop.trajectory.solver import TrajectoryCommand

    tracks = {
        "LEAD": TrackNode(id="LEAD", type="lead", max_cars=10, max_length_units=100),
        "O1": TrackNode(id="O1", type="outbound", max_cars=4, max_length_units=20),
    }
    edges = [SwitchEdge(id="SW1", from_track="LEAD", to_track="O1", length_m=100.0)]
    graph = YardGraph(tracks, edges)
    cars = [
        FreightCar(id="A", destination="X", length_units=12, mass_t=10.0),
        FreightCar(id="B", destination="X", length_units=10, mass_t=10.0),
    ]
    commands = [
        TrajectoryCommand.push("LEAD", "O1", ["A"]),
        TrajectoryCommand.push("LEAD", "O1", ["B"]),
    ]
    assert _simulate_capacity(graph, cars, commands) is False


# ── 28. Optimize stage must fail capacity when THROW hits a failed switch ─
def test_optimize_flags_throw_on_failed_switch():
    """Direct contract: capacity_verified is false when commands THROW a failed switch."""
    from pathlib import Path

    from fyop.residual.physics_gate import optimize
    from fyop.trajectory.solver import OccupancyTrajectory, TrajectoryCommand

    obs_dir = TB3_OBS_P9W2
    if not os.path.isdir(obs_dir):
        pytest.skip("obs-p9w2 fixture not found")

    original = OccupancyTrajectory.sequence

    def _inject_failed_throw(self):
        self._commands = [TrajectoryCommand.throw_switch("SW5")]
        self._loco_track = "LEAD"
        self._capacity_ok = True
        self._total_distance_m = 0.0

    OccupancyTrajectory.sequence = _inject_failed_throw
    try:
        _clean()
        r1 = _run(["ingest"], env_override={"HFSY_YARD_DIR": obs_dir})
        assert r1.returncode == 0, r1.stderr
        # Call optimize in-process so the trajectory monkeypatch applies.
        optimize(Path(STATE), Path(obs_dir))
        validated = _load(os.path.join(STATE, "shunting-validated.json"))
        assert validated.get("capacity_verified") is False, (
            "optimize must set capacity_verified false when THROW_SWITCH targets a failed switch"
        )
    finally:
        OccupancyTrajectory.sequence = original


# ── 29. Path search must skip failed switch edges ─────────────────────
def test_path_search_skips_failed_switches():
    """Direct contract: trajectory path finder must not traverse failed switch ids."""
    from fyop.consist.cars import FreightCar
    from fyop.topology.graph import SwitchEdge, TrackNode, YardGraph
    from fyop.trajectory.solver import OccupancyTrajectory

    tracks = {
        "LEAD": TrackNode(id="LEAD", type="lead", max_cars=10, max_length_units=100),
        "C1": TrackNode(id="C1", type="classification", max_cars=4, max_length_units=40),
        "O1": TrackNode(id="O1", type="outbound", max_cars=4, max_length_units=40),
    }
    edges = [
        SwitchEdge(id="SW_BAD", from_track="C1", to_track="O1", length_m=50.0),
        SwitchEdge(id="SW_OK1", from_track="C1", to_track="LEAD", length_m=100.0),
        SwitchEdge(id="SW_OK2", from_track="LEAD", to_track="O1", length_m=100.0),
    ]
    graph = YardGraph(tracks, edges)
    cars = [FreightCar(id="A", destination="X", length_units=5, mass_t=10.0)]
    traj = OccupancyTrajectory(graph, cars, ["X"], {"X": "O1"}, {"SW_BAD"})
    path = traj._find_path("C1", "O1")
    assert path is not None, "alternate residual path via LEAD must exist"
    assert all(e.id != "SW_BAD" for e in path), "failed switch SW_BAD must be skipped"
    assert [e.id for e in path] == ["SW_OK1", "SW_OK2"]
