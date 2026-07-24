"""Track occupancy state and capacity guard."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fyop.consist.cars import FreightCar
    from fyop.topology.graph import TrackNode


class TrackState:
    """Mutable list of cars currently occupying a track."""

    def __init__(self, track_id: str) -> None:
        self.track_id = track_id
        self._cars: list[FreightCar] = []

    @property
    def cars(self) -> list[FreightCar]:
        return self._cars

    def car_count(self) -> int:
        return len(self._cars)

    def total_length_units(self) -> int:
        return sum(c.length_units for c in self._cars)

    def total_mass_t(self) -> float:
        return sum(c.mass_t for c in self._cars)

    def add_car(self, car: FreightCar) -> None:
        self._cars.append(car)


class OccupancyGuard:
    """Capacity feasibility checks before pushing a car onto a track."""

    @staticmethod
    def can_push(track: TrackNode, state: TrackState, car: FreightCar) -> bool:
        """Return True only when BOTH car-count AND length-unit limits permit the push."""
        if state.car_count() + 1 > track.max_cars:
            return False
        return state.total_length_units() + car.length_units <= track.max_length_units
