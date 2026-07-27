"""Emit the lookup table used by the overfit-answer-map baseline.

The baseline it feeds recognises the public traces and nothing else, which is
what lets a test show that memorising the shipped examples cannot carry the
hidden battery.
"""

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
TASK = os.path.dirname(os.path.dirname(HERE))
VISIBLE_DIR = os.path.join(TASK, "environment", "inputs")
GOLDEN_DIR = os.path.join(TASK, "tests", "golden")


def literal(payload):
    return "".join(f"\\{byte:03o}" for byte in payload)


def main():
    rows = []
    for path in sorted(glob.glob(os.path.join(VISIBLE_DIR, "*.bin"))):
        base = os.path.join(GOLDEN_DIR, os.path.basename(path))
        with open(path, "rb") as handle:
            payload = handle.read()
        with open(base + ".out", "rb") as handle:
            answer = handle.read()
        with open(base + ".code", encoding="ascii") as handle:
            code = int(handle.read())
        rows.append(
            f'    {{"{literal(payload)}", {len(payload)}, '
            f'"{literal(answer)}", {len(answer)}, {code}}},'
        )
    target = os.path.join(HERE, "visible_answers.inc")
    with open(target, "w", encoding="ascii") as handle:
        handle.write("\n".join(rows) + "\n")
    sys.stdout.write(f"answers={len(rows)}\n")


if __name__ == "__main__":
    main()
