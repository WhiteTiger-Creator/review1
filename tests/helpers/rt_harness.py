from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

APP = Path("/app")
SOCKET = APP / "state" / "rt.sock"
OUTPUT = Path("/output/rt-runs")
AUDIT = Path("/var/log/rt-daemon/audit.log")
SIGN_SEED = Path("/tests/fixtures/signing-key.seed")

_daemon: subprocess.Popen | None = None


def reset_runtime() -> None:
    global _daemon
    if _daemon and _daemon.poll() is None:
        os.kill(_daemon.pid, 15)
        try:
            _daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _daemon.kill()
    _daemon = None
    for p in [SOCKET, APP / "state" / "cache"]:
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    if AUDIT.exists():
        AUDIT.unlink()
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (APP / "state").mkdir(parents=True, exist_ok=True)


def start_daemon() -> None:
    global _daemon
    reset_runtime()
    _daemon = subprocess.Popen(
        [
            "python3",
            "-c",
            "from rt_core.lane_a.server import run_daemon; run_daemon('/app/config/rt.toml','/app/state/rt.sock','/app/state')",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        if SOCKET.exists():
            os.chmod(SOCKET, 0o666)
            return
        time.sleep(0.1)
    raise RuntimeError("rt-daemon socket not ready")


def socket_request(payload: dict) -> dict:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(str(SOCKET))
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        conn.sendall(struct.pack("!I", len(body)) + body)
        header = conn.recv(4)
        length = struct.unpack("!I", header)[0]
        return json.loads(conn.recv(length))
    finally:
        conn.close()


def write_module(ops: list[dict], work: Path) -> tuple[Path, str]:
    work.mkdir(parents=True, exist_ok=True)
    mod = work / "guest.json"
    mod.write_text(json.dumps({"ops": ops}, indent=2) + "\n", encoding="utf-8")
    return mod, hashlib.sha256(mod.read_bytes()).hexdigest()


def _priv() -> Ed25519PrivateKey:
    seed = SIGN_SEED.read_bytes()
    return Ed25519PrivateKey.from_private_bytes(seed)


def sign_manifest(doc: dict) -> dict:
    script = (
        "import json, sys\n"
        "from rt_core.lane_b.doc_lane import digest_bytes\n"
        "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey\n"
        f"seed = open({json.dumps(str(SIGN_SEED))}, 'rb').read()\n"
        "doc = json.loads(sys.stdin.read())\n"
        "priv = Ed25519PrivateKey.from_private_bytes(seed)\n"
        "out = dict(doc)\n"
        "out['signature'] = priv.sign(digest_bytes(doc)).hex()\n"
        "print(json.dumps(out))\n"
    )
    proc = subprocess.run(
        ["python3", "-c", script],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def kv_get(tenant: str, key: str) -> str:
    db = Path(f"/data/tenants/{tenant}/kv.sqlite")
    if not db.exists():
        return ""
    proc = subprocess.run(
        ["sqlite3", str(db), f"SELECT v FROM kv WHERE k='{key}';"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def read_result(rid: str) -> dict:
    return json.loads((OUTPUT / rid / "result.json").read_text(encoding="utf-8"))
