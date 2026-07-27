"""Print lowercase hex sha256 of stdin or of a file path argument."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) > 1:
        with Path(sys.argv[1]).open("rb") as fh:
            data = fh.read()
    else:
        data = sys.stdin.buffer.read()
    sys.stdout.write(hashlib.sha256(data).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
