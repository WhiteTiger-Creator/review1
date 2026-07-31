"""Stub bundler for the vault driver. Oracle replaces this file."""

from __future__ import annotations

import argparse
import sys


def merge_driver_parts(nav_path: str, play_path: str, out_path: str) -> None:
    raise NotImplementedError("bundle_player stub: merge_driver_parts unset")


def stage_autoplay(src_path: str, dst_path: str) -> None:
    raise NotImplementedError("bundle_player stub: stage_autoplay unset")


def drive_seed(autoplay_path: str, seed: str, out_path: str) -> None:
    raise NotImplementedError("bundle_player stub: drive_seed unset")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["merge", "stage", "run"])
    parser.add_argument("--seed", default="nominal")
    parser.add_argument("--out", default="/app/output/vault_state.json")
    return parser.parse_args(argv)


def bundle_cli(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.command == "merge":
        merge_driver_parts(
            "/app/environment/tools/nav_core.js",
            "/app/environment/driver/play_core.js",
            "/app/environment/tools/ref_player.js",
        )
    elif args.command == "stage":
        stage_autoplay(
            "/app/environment/tools/ref_player.js",
            "/app/output/autoplay.js",
        )
    else:
        drive_seed("/app/output/autoplay.js", args.seed, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(bundle_cli())
