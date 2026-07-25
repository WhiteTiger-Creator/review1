from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from rt_core.errors import HostError


def run_import(op: str, resource: str, state: dict, value: str | None = None) -> str:
    tenant = state["tenant"]
    roots = state.get("tenant_roots") or state.get("roots") or {}
    root = roots.get(tenant, f"/data/tenants/{tenant}")
    caps = state["caps"]
    meter = state["meter"]
    if meter.host_calls <= 0:
        raise HostError("host-call-budget-exhausted")
    meter.host_calls -= 1
    if op not in caps:
        raise HostError("capability-denied")
    if op == "fs.read":
        path = Path(root) / resource
        if ".." in resource or path.resolve().as_posix().find(f"/data/tenants/{tenant}") != 0:
            raise HostError("path-denied")
        return path.read_text(encoding="utf-8") if path.exists() else ""
    if op == "fs.write":
        path = Path(root) / resource
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value or "", encoding="utf-8")
        return "ok"
    if op == "env.read":
        env = json.loads(Path(root).joinpath(".env.json").read_text(encoding="utf-8"))
        return env.get(resource, "")
    if op == "clock.read":
        return Path("/app/config/clock").read_text(encoding="utf-8").strip()
    if op == "socket.connect":
        gate = Path(f"/app/state/gates/{tenant}-{resource}.pipe")
        gate.parent.mkdir(parents=True, exist_ok=True)
        if not gate.exists():
            os.mkfifo(str(gate))
        with open(gate, "w", encoding="utf-8") as fh:
            fh.write("ping\n")
        return "sent"
    if op == "kv.write":
        db = Path(root) / "kv.sqlite"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        conn.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (resource, value or ""))
        conn.commit()
        conn.close()
        return "ok"
    if op == "kv.read":
        db = Path(root) / "kv.sqlite"
        if not db.exists():
            return ""
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT v FROM kv WHERE k=?", (resource,)).fetchone()
        conn.close()
        return row[0] if row else ""
    raise HostError("unknown-import")
