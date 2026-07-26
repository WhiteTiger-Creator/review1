"""Freight consist parser: cars and plan from yard JSON inputs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FreightCar:
    id: str
    destination: str
    length_units: int
    mass_t: float


@dataclass
class ConsistPlan:
    destination_order: list[str]
    outbound_assignments: dict[str, str]


def load_consist(yard_dir: Path) -> tuple[str, list[FreightCar]]:
    """Return (train_id, cars) from consist.json preserving array order."""
    raw = json.loads((yard_dir / "consist.json").read_text())
    train_id: str = raw["train_id"]
    cars: list[FreightCar] = [
        FreightCar(
            id=c["id"],
            destination=c["destination"],
            length_units=int(c["length_units"]),
            mass_t=float(c["mass_t"]),
        )
        for c in raw["cars"]
    ]
    return train_id, cars


def load_plan(yard_dir: Path) -> ConsistPlan:
    """Return destination_order and outbound_assignments from plan.json."""
    raw = json.loads((yard_dir / "plan.json").read_text())
    return ConsistPlan(
        destination_order=list(raw["destination_order"]),
        outbound_assignments=dict(raw["outbound_assignments"]),
    )


def load_failures(yard_dir: Path) -> dict:
    """Return full failures JSON object, or empty dict when file is absent."""
    fail_path = yard_dir / "failures.json"
    if fail_path.exists():
        return json.loads(fail_path.read_text())
    return {}


def failed_switch_ids(failures_obj: dict) -> set[str]:
    """Extract the set of failed switch id strings from a failures dict."""
    return set(failures_obj.get("failed_switches", []))
