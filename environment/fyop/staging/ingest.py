"""Ingest stage: build staging hash, write yard-staging.json and ingest-snapshot.json."""
from __future__ import annotations

import datetime
import json
import json as _json
import os
from pathlib import Path

from fyop.consist.cars import load_consist, load_failures
from fyop.staging.jsonutil import pretty, sha256hex


def ingest(yard_dir: Path, state_dir: Path) -> None:
    """Load yard corpus, compute staging_hash, and write staging + snapshot files."""
    yard_dir = Path(yard_dir)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    train_id, cars = load_consist(yard_dir)
    topology = json.loads((yard_dir / "topology.json").read_text())
    plan = json.loads((yard_dir / "plan.json").read_text())
    failures = load_failures(yard_dir)

    cars_arr = [
        {"id": c.id, "destination": c.destination,
         "length_units": c.length_units, "mass_t": c.mass_t}
        for c in cars
    ]

    hash_body = {
        "train_id": train_id,
        "topology": topology,
        "consist": cars_arr,
        "plan": plan,
        "failures": failures,
    }
    staging_hash = sha256hex(_json.dumps(hash_body, indent=2))

    total_len = sum(c.length_units for c in cars)
    total_mass = sum(c.mass_t for c in cars)
    destinations_sorted = sorted({c.destination for c in cars})

    staging = {
        "train_id": train_id,
        "staged_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "topology": topology,
        "consist": cars_arr,
        "plan": plan,
        "failures": failures,
        "staging_hash": staging_hash,
    }
    (state_dir / "yard-staging.json").write_text(pretty(staging))

    snapshot = {
        "train_id": train_id,
        "car_count": len(cars),
        "total_length_units": total_len,
        "total_mass_t": total_mass,
        "destinations": destinations_sorted,
        "yard_dir": str(yard_dir),
        "staging_hash": staging_hash,
    }
    (state_dir / "ingest-snapshot.json").write_text(pretty(snapshot))


def read_staging(state_dir: Path) -> dict:
    """Read and parse yard-staging.json."""
    return json.loads((state_dir / "yard-staging.json").read_text())


def read_validated(state_dir: Path) -> dict:
    """Read and parse shunting-validated.json."""
    return json.loads((state_dir / "shunting-validated.json").read_text())


def get_yard_dir() -> Path:
    """Resolve active yard directory from env var or default."""
    env_val = os.environ.get("HFSY_YARD_DIR", "").strip()
    if env_val:
        return Path(env_val)
    return Path("/app/yard-alpha")
