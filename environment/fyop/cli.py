"""YOD occupancy-dynamics driver for the freight-yard spatial graph study."""
from __future__ import annotations

import sys
from pathlib import Path

from fyop.export.atlas import export
from fyop.residual.physics_gate import optimize
from fyop.staging.ingest import get_yard_dir, ingest

STATE_DIR = Path("/app/state")
OUTPUT_DIR = Path("/app/output")


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: fyop-atlas <ingest|optimize|export>", file=sys.stderr)
        sys.exit(1)

    yard_dir = get_yard_dir()
    cmd = args[0]

    if cmd == "ingest":
        ingest(yard_dir, STATE_DIR)
        print("Ingest complete.")
    elif cmd == "optimize":
        optimize(STATE_DIR, yard_dir)
        print("Optimize complete.")
    elif cmd == "export":
        export(STATE_DIR, OUTPUT_DIR)
        print("Export complete.")
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
