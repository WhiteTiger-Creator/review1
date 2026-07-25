"""Optimize stage: run trajectory, validate capacity and closure, write shunting-validated.json."""
from __future__ import annotations

from pathlib import Path

from fyop.consist.cars import FreightCar, failed_switch_ids
from fyop.residual.reach import can_loco_reach_lead
from fyop.staging.ingest import read_staging
from fyop.staging.jsonutil import canonical, pretty, sha256hex
from fyop.topology.graph import SwitchEdge, TrackNode, YardGraph
from fyop.trajectory.solver import OccupancyTrajectory, TrajectoryCommand


def _build_graph_from_staging(staging: dict) -> YardGraph:
    topo = staging["topology"]
    tracks: dict[str, TrackNode] = {}
    for t in topo["tracks"]:
        tracks[t["id"]] = TrackNode(
            id=t["id"], type=t["type"],
            max_cars=int(t["max_cars"]),
            max_length_units=int(t["max_length_units"]),
        )
    edges = [
        SwitchEdge(
            id=s["id"], from_track=s["from_track"],
            to_track=s["to_track"], length_m=float(s["length_m"]),
        )
        for s in topo["switches"]
    ]
    return YardGraph(tracks, edges)


def _build_cars(staging: dict) -> list[FreightCar]:
    return [
        FreightCar(
            id=c["id"], destination=c["destination"],
            length_units=int(c["length_units"]), mass_t=float(c["mass_t"]),
        )
        for c in staging["consist"]
    ]


def _simulate_capacity(
    graph: YardGraph,
    cars: list[FreightCar],
    commands: list[TrajectoryCommand],
) -> bool:
    """Replay PUSH/PULL commands and verify track limits are never violated."""
    track_cars: dict[str, list[str]] = {tid: [] for tid in graph.track_ids()}
    track_cars["LEAD"] = [c.id for c in cars]

    for cmd in commands:
        if cmd.type not in ("PUSH", "PULL"):
            continue
        fr = cmd.from_track
        to = cmd.to_track
        for cid in cmd.car_ids:
            if fr and cid in track_cars.get(fr, []):
                track_cars[fr].remove(cid)
            if to:
                track_cars.setdefault(to, []).append(cid)
        node = graph.get_track(to) if to else None
        if node is None:
            continue
        on_track = track_cars.get(to, [])
        if len(on_track) > node.max_cars:
            return False
    return True


def optimize(state_dir: Path, _yard_dir: Path) -> None:
    """Read staging, run trajectory sequence, validate, write shunting-validated.json."""
    state_dir = Path(state_dir)
    staging = read_staging(state_dir)

    train_id: str = staging["train_id"]
    staging_hash: str = staging["staging_hash"]

    graph = _build_graph_from_staging(staging)
    cars = _build_cars(staging)

    plan = staging["plan"]
    destination_order: list[str] = list(plan["destination_order"])
    outbound_assignments: dict[str, str] = dict(plan["outbound_assignments"])

    failures_obj: dict = staging.get("failures", {})
    failed: set[str] = failed_switch_ids(failures_obj)

    seq = OccupancyTrajectory(graph, cars, destination_order, outbound_assignments, failed)
    seq.sequence()

    closure_ok = can_loco_reach_lead(graph, seq.loco_end_track, failed)
    capacity_ok = seq.capacity_ok and _simulate_capacity(graph, cars, seq.commands)

    commands_list = [cmd.to_dict() for cmd in seq.commands]

    outbound_blocks = dict(seq.get_outbound_blocks().items())

    validated: dict = {
        "train_id": train_id,
        "staging_hash": staging_hash,
        "commands": commands_list,
        "total_distance_m": seq.total_distance_m,
        "outbound_blocks": outbound_blocks,
        "loco_end_track": seq.loco_end_track,
        "capacity_verified": capacity_ok,
        "closure_verified": closure_ok,
    }

    seal = sha256hex(canonical(validated))
    validated["validation_seal"] = seal

    (state_dir / "shunting-validated.json").write_text(pretty(validated))
