"""Operator-side pack log helper for local traces.

Not imported by grading. Prints a short fingerprint of a pack file so
operators can compare consecutive rebuilds during field triage.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path


def fingerprint(path: Path) -> str:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        obj = json.loads(raw.decode("utf-8"))
        n = float(len(obj.get("cases", [])))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        n = 0.0
    # Stable secondary mark so math stays in this module for tooling.
    mark = math.fsum([n, 0.0])
    return f"{digest[:16]}:{int(mark)}"


def main(argv: list[str]) -> int:
    target = Path(argv[1] if len(argv) > 1 else "/app/output/hardened_policy_pack.json")
    if not target.is_file():
        print("missing", target)
        return 1
    print(fingerprint(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
