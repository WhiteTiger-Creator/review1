from __future__ import annotations

import json
import os
import socket
import struct
import threading
from pathlib import Path

from rt_core.lane_i.invoke import run_invocation


def run_daemon(config_path: str, sock_path: str, state_dir: str) -> None:
    cfg = Path(config_path)
    sock_file = Path(sock_path)
    if sock_file.exists():
        sock_file.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_file))
    os.chmod(sock_path, 0o666)
    server.listen(8)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=_handle, args=(conn, cfg, state_dir), daemon=True).start()


def _handle(conn: socket.socket, cfg: Path, state_dir: str) -> None:
    try:
        header = conn.recv(4)
        if len(header) < 4:
            return
        length = struct.unpack("!I", header)[0]
        body = b""
        while len(body) < length:
            chunk = conn.recv(length - len(body))
            if not chunk:
                break
            body += chunk
        req = json.loads(body.decode("utf-8"))
        resp = run_invocation(req, cfg, state_dir)
        out = json.dumps(resp, sort_keys=True).encode("utf-8")
        conn.sendall(struct.pack("!I", len(out)) + out)
    finally:
        conn.close()
