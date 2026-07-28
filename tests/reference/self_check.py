#!/usr/bin/env python3
"""Self-check CLI for the reference reconciler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reference.engine import WholeRunFatal, reconcile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference reconciler self-check")
    parser.add_argument(
        "data_dir",
        nargs="?",
        default="/app/data",
        help="Data directory (default: /app/data)",
    )
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)

    try:
        report = reconcile(data_dir)
    except WholeRunFatal as exc:
        print(f"{exc.reason_token}:", file=sys.stderr)
        return 1

    summary = report["summary"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        f"request_rows={len(report['request_rows'])} "
        f"package_selection_rows={len(report['package_selection_rows'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
