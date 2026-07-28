"""Command line entry point for the offline PMT calibration pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

from reducectl.run import reduce_calibration

ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = Path("/app/output/hv_gain_table.json")
DEFAULT_STATE = Path("/app/state/hv_replay_ledger.json")


def _usage(stream) -> None:
    stream.write(
        "usage: python3 /app/environment/hvreduce.py calibrate <profile>\n"
        "       python3 /app/environment/hvreduce.py calibrate <profile> "
        "--report <path> --state <path>\n"
        "Profiles are declared in /app/environment/runbook/campaign.toml.\n"
    )


def _option(argv: list[str], flag: str, fallback: Path) -> Path:
    if flag not in argv:
        return fallback
    index = argv.index(flag)
    if index + 1 >= len(argv):
        return fallback
    return Path(argv[index + 1])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _usage(sys.stdout)
        return 0 if argv and argv[0] in ("-h", "--help") else 1
    if argv[0] != "calibrate" or len(argv) < 2:
        _usage(sys.stderr)
        return 1

    profile = argv[1]
    report_path = _option(argv, "--report", DEFAULT_REPORT)
    state_path = _option(argv, "--state", DEFAULT_STATE)

    try:
        reduce_calibration(ROOT, profile, report_path, state_path)
    except (OSError, ValueError) as err:
        sys.stderr.write(f"{err}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
