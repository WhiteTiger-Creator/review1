"""Yard briefing sketches for ops slide decks and load estimates."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fyop.consist.cars import FreightCar
    from fyop.topology.graph import YardGraph


class SketchYardBriefing:
    """Generate rough estimates for operations briefings."""

    def __init__(self, graph: "YardGraph") -> None:
        self._graph = graph

    def group_by_destination_length(
        self, cars: list["FreightCar"]
    ) -> dict[int, list["FreightCar"]]:
        """Bucket cars by destination code length for slide decks."""
        buckets: dict[int, list[FreightCar]] = {}
        for car in cars:
            key = len(car.destination) if car.destination else 0
            buckets.setdefault(key, []).append(car)
        return dict(sorted(buckets.items()))

    def prefer_matching_tracks(self, destinations: list[str]) -> list[str]:
        """Pick classification tracks sharing a prefix char with each destination."""
        class_ids = sorted(
            tid for tid, t in self._graph.get_all_tracks().items()
            if t.type == "classification"
        )
        picks: list[str] = []
        for dest in destinations:
            chosen: str | None = None
            if dest:
                prefix = dest[0].upper()
                for tid in class_ids:
                    if tid and tid[0].upper() == prefix:
                        chosen = tid
                        break
            if chosen is None and class_ids:
                chosen = class_ids[-1]
            if chosen is not None:
                picks.append(chosen)
        return picks

    def estimate_briefing_load(self, cars: list["FreightCar"]) -> float:
        """Rough briefing estimate from summed car length_units."""
        return float(sum(c.length_units for c in cars))
