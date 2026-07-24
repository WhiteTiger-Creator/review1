"""Occupancy trajectory: YOD discrete dynamical sequence with path-integral observable."""
from __future__ import annotations

from collections import deque
from typing import Optional

from fyop.consist.cars import FreightCar
from fyop.occupancy.guard import OccupancyGuard, TrackState
from fyop.topology.graph import SwitchEdge, YardGraph


class TrajectoryCommand:
    def __init__(
        self,
        cmd_type: str,
        *,
        switch_id: Optional[str] = None,
        from_track: Optional[str] = None,
        to_track: Optional[str] = None,
        car_ids: Optional[list[str]] = None,
    ) -> None:
        self.type = cmd_type
        self.switch_id = switch_id
        self.from_track = from_track
        self.to_track = to_track
        self.car_ids: list[str] = car_ids or []

    @staticmethod
    def throw_switch(switch_id: str) -> "TrajectoryCommand":
        return TrajectoryCommand("THROW_SWITCH", switch_id=switch_id)

    @staticmethod
    def push(from_track: str, to_track: str, car_ids: list[str]) -> "TrajectoryCommand":
        return TrajectoryCommand("PUSH", from_track=from_track, to_track=to_track, car_ids=list(car_ids))

    @staticmethod
    def move_loco(from_track: str, to_track: str) -> "TrajectoryCommand":
        return TrajectoryCommand("MOVE_LOCO", from_track=from_track, to_track=to_track)

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.switch_id is not None:
            d["switch_id"] = self.switch_id
        if self.from_track is not None:
            d["from_track"] = self.from_track
        if self.to_track is not None:
            d["to_track"] = self.to_track
        if self.car_ids:
            d["car_ids"] = list(self.car_ids)
        return d


class OccupancyTrajectory:
    """Compute the discrete occupancy-dynamics shunting sequence on the yard graph."""

    def __init__(
        self,
        graph: YardGraph,
        consist: list[FreightCar],
        destination_order: list[str],
        outbound_assignments: dict[str, str],
        failed_switches: set[str],
    ) -> None:
        self._graph = graph
        self._consist = list(consist)
        self._destination_order = list(destination_order)
        self._outbound_assignments = dict(outbound_assignments)
        self._failed_switches = set(failed_switches)

        self._track_states: dict[str, TrackState] = {
            tid: TrackState(tid) for tid in graph.track_ids()
        }
        self._commands: list[TrajectoryCommand] = []
        self._total_distance_m: float = 0.0
        self._loco_track: str = "LEAD"
        self._capacity_ok: bool = True

        lead_state = self._track_states["LEAD"]
        for car in consist:
            lead_state.add_car(car)

    def sequence(self) -> None:
        """Run the full three-phase shunting sequence."""
        dests = self._ordered_destinations()
        dest_to_class = self._assign_classification(dests)

        for car in list(self._consist):
            class_track = dest_to_class.get(car.destination)
            if class_track is None:
                continue
            if self._find_car_track(car) != "LEAD":
                continue
            self._move_car(car, "LEAD", class_track)

        for dest in dests:
            class_track = dest_to_class.get(dest)
            out_track = self._outbound_assignments.get(dest)
            if class_track is None or out_track is None:
                continue
            cs = self._track_states.get(class_track)
            if cs is None:
                continue
            to_move = [c for c in list(cs.cars) if c.destination == dest]
            for car in to_move:
                self._move_car(car, class_track, out_track)

    def _ordered_destinations(self) -> list[str]:
        return sorted(self._outbound_assignments.keys())

    def _assign_classification(self, dests: list[str]) -> dict[str, str]:
        """Assign each destination to a classification track by tightest length slack."""
        dest_len: dict[str, int] = {d: 0 for d in dests}
        dest_count: dict[str, int] = {d: 0 for d in dests}
        for car in self._consist:
            if car.destination not in dest_len:
                continue
            dest_len[car.destination] += car.length_units
            dest_count[car.destination] += 1

        class_ids = self._usable_classification_tracks()
        result: dict[str, str] = {}
        used: set[str] = set()

        by_size = sorted(dests, key=lambda d: dest_len[d], reverse=True)

        for dest in by_size:
            best: Optional[str] = None
            best_slack = float("inf")
            out_track = self._outbound_assignments.get(dest)
            for cid in class_ids:
                if cid in used:
                    continue
                track = self._graph.get_track(cid)
                if track is None:
                    continue
                need_len = dest_len[dest]
                need_cars = dest_count[dest]
                if need_cars > track.max_cars:
                    continue
                if need_len > track.max_length_units:
                    continue
                if out_track is not None:
                    direct = self._find_path(cid, out_track)
                    can_via_lead = (
                        self._find_path(cid, "LEAD") is not None
                        and self._find_path("LEAD", out_track) is not None
                    )
                    if direct is None and not can_via_lead:
                        continue
                slack = track.max_length_units - need_len
                if slack < best_slack:
                    best_slack = slack
                    best = cid
            if best is not None:
                result[dest] = best
                used.add(best)
        return result

    def _usable_classification_tracks(self) -> list[str]:
        class_ids = [
            tid for tid, t in self._graph.get_all_tracks().items()
            if t.type == "classification" and self._can_reach_lead(tid)
        ]
        return sorted(class_ids)

    def _can_reach_lead(self, track_id: str) -> bool:
        if track_id == "LEAD":
            return True
        return self._find_path(track_id, "LEAD") is not None

    def _find_car_track(self, car: FreightCar) -> Optional[str]:
        for tid, state in self._track_states.items():
            if car in state.cars:
                return tid
        return None

    def _move_car(self, car: FreightCar, from_id: str, to_id: str) -> None:
        if from_id == to_id:
            return
        to_node = self._graph.get_track(to_id)
        to_state = self._track_states.get(to_id)
        if to_node is None or to_state is None:
            self._capacity_ok = False
            return
        if not OccupancyGuard.can_push(to_node, to_state, car):
            self._capacity_ok = False
            return

        path = self._find_path(from_id, to_id)
        if path is None:
            to_lead = self._find_path(from_id, "LEAD")
            from_lead = self._find_path("LEAD", to_id)
            if to_lead is not None and from_lead is not None and from_id != "LEAD":
                self._traverse_path(to_lead, from_id, "LEAD", car)
                from_id = "LEAD"
                path = from_lead
        if path is None:
            self._capacity_ok = False
            return
        self._traverse_path(path, from_id, to_id, car)

    def _traverse_path(
        self,
        path: list[SwitchEdge],
        start: str,
        end: str,  # noqa: ARG002
        car: Optional[FreightCar],
    ) -> None:
        cur = start
        for edge in path:
            nxt = edge.to_track if edge.from_track == cur else edge.from_track
            self._commands.append(TrajectoryCommand.throw_switch(edge.id))
            if car is not None:
                self._commands.append(TrajectoryCommand.push(cur, nxt, [car.id]))
                self._track_states[cur].cars.remove(car)
                self._track_states[nxt].add_car(car)
            else:
                self._commands.append(TrajectoryCommand.move_loco(cur, nxt))
            self._total_distance_m += 1.0
            self._loco_track = nxt
            cur = nxt

    def _find_path(self, from_id: str, to_id: str) -> Optional[list[SwitchEdge]]:
        """BFS path search between tracks on the yard graph."""
        if from_id == to_id:
            return []
        came_via: dict[str, SwitchEdge] = {}
        prev: dict[str, str] = {}
        seen: set[str] = {from_id}
        q: deque[str] = deque([from_id])
        while q:
            cur = q.popleft()
            for edge in self._graph.edges_from(cur):
                nxt = edge.to_track if edge.from_track == cur else edge.from_track
                if nxt in seen:
                    continue
                seen.add(nxt)
                came_via[nxt] = edge
                prev[nxt] = cur
                if nxt == to_id:
                    path: list[SwitchEdge] = []
                    walk = to_id
                    while walk != from_id:
                        path.append(came_via[walk])
                        walk = prev[walk]
                    path.reverse()
                    return path
                q.append(nxt)
        return None

    @property
    def commands(self) -> list[TrajectoryCommand]:
        return list(self._commands)

    @property
    def total_distance_m(self) -> float:
        return self._total_distance_m

    @property
    def loco_end_track(self) -> str:
        return self._loco_track

    @property
    def track_states(self) -> dict[str, TrackState]:
        return dict(self._track_states)

    @property
    def capacity_ok(self) -> bool:
        return self._capacity_ok

    def get_outbound_blocks(self) -> dict[str, list[dict]]:
        """Return outbound blocks in destination_order, preserving inbound consist order."""
        inbound_index: dict[str, int] = {car.id: i for i, car in enumerate(self._consist)}
        blocks: dict[str, list[dict]] = {}
        for dest in self._ordered_destinations():
            out_track = self._outbound_assignments.get(dest)
            if out_track is None:
                continue
            state = self._track_states.get(out_track)
            if state is None:
                continue
            cars = sorted(
                [c for c in state.cars if c.destination == dest],
                key=lambda c: inbound_index.get(c.id, len(self._consist)),
            )
            if not cars:
                continue
            blocks.setdefault(out_track, []).append({
                "destination": dest,
                "car_ids": [c.id for c in cars],
            })
        return blocks
