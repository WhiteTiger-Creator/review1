from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rt_core.lane_a.server import run_daemon
from rt_core.lane_c.code_lane import CodeStore
from rt_core.lane_e.plan_lane import PlanStore


def hostd_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rt-daemon")
    p.add_argument("--config", default="/app/config/rt.toml")
    p.add_argument("--socket", default="/app/state/rt.sock")
    p.add_argument("--state-dir", default="/app/state")
    args = p.parse_args(argv)
    run_daemon(args.config, args.socket, args.state_dir)
    return 0


def run_main(argv: list[str] | None = None) -> int:
    import socket
    import struct

    p = argparse.ArgumentParser(prog="rt-run")
    p.add_argument("--socket", required=True)
    p.add_argument("--tenant", required=True)
    p.add_argument("--module", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--grant", default="")
    p.add_argument("--output-dir", default="/output/rt-runs")
    args = p.parse_args(argv)
    payload = {
        "tenant": args.tenant,
        "module": args.module,
        "manifest": args.manifest,
    }
    if args.grant:
        payload["grant"] = args.grant
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.connect(args.socket)
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    conn.sendall(struct.pack("!I", len(body)) + body)
    header = conn.recv(4)
    length = struct.unpack("!I", header)[0]
    resp = json.loads(conn.recv(length))
    print(json.dumps(resp, indent=2))
    return 0 if resp.get("ok") else 1


def cachectl_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rt-cachectl")
    p.add_argument("--socket", required=True)
    p.add_argument("command", choices=["stats", "inspect", "clear-invalid"])
    p.parse_args(argv)
    compiled = CodeStore(Path("/app/state/cache/compiled"))
    linked = PlanStore(Path("/app/state/cache/linked"))
    stats = {
        "compiled_entries": len(list((Path("/app/state/cache/compiled")).glob("*.bin"))),
        "linked_entries": len(list((Path("/app/state/cache/linked")).glob("*.json"))),
        "memory_compiled": len(compiled.mem),
        "memory_linked": len(linked.mem),
    }
    print(json.dumps(stats, indent=2))
    return 0


def fault_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rt-fault-runner")
    p.add_argument("--list", action="store_true")
    p.add_argument("--component")
    p.add_argument("--failpoint")
    p.add_argument("--request")
    args = p.parse_args(argv)
    if args.list:
        points = [
            "host:after_compiled_temp_fsync",
            "host:after_compiled_publish",
            "host:after_link_plan_temp_fsync",
            "host:after_link_plan_publish",
            "policy:after_policy_snapshot_fsync",
            "policy:after_policy_publish",
        ]
        for pt in points:
            print(pt)
        return 0
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(2)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "hostd":
        raise SystemExit(hostd_main(rest))
    if cmd == "run":
        raise SystemExit(run_main(rest))
    if cmd == "cachectl":
        raise SystemExit(cachectl_main(rest))
    if cmd == "fault":
        raise SystemExit(fault_main(rest))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
