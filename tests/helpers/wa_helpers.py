"""Narrow specification-derived helpers for verifier tests."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
TEST_DIR = Path(os.environ.get("TEST_DIR", Path(__file__).resolve().parents[1]))
AS_OF = "2026-07-01T12:00:00Z"
_SEED_DB = TEST_DIR / "fixtures" / "audit.sqlite"
CANONICAL_DB = _SEED_DB if _SEED_DB.is_file() else APP_ROOT / "data" / "audit.sqlite"
KEYS_DIR = TEST_DIR / "helpers" / "keys"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def load_private_key(name: str) -> ec.EllipticCurvePrivateKey:
    pem = (KEYS_DIR / name).read_bytes()
    return serialization.load_pem_private_key(pem, password=None)


def auth_data(rp_id: str, flags: int, sign_count: int) -> bytes:
    return sha256(rp_id.encode("utf-8")) + bytes([flags]) + struct.pack(">I", sign_count)


def client_data_bytes(challenge: bytes, origin: str, **extra: Any) -> bytes:
    """Compact clientDataJSON with serde_json-stable alphabetical member order."""
    obj: dict[str, Any] = {
        "challenge": b64url(challenge),
        "origin": origin,
        "type": "webauthn.get",
    }
    obj.update(extra)
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )


def sign_assertion(sk: ec.EllipticCurvePrivateKey, ad: bytes, cdata: bytes) -> bytes:
    msg = ad + sha256(cdata)
    return sk.sign(msg, ec.ECDSA(hashes.SHA256()))


def copy_fixture_db() -> Path:
    td = Path(tempfile.mkdtemp(prefix="wa-db-"))
    dst = td / "audit.sqlite"
    shutil.copy2(CANONICAL_DB, dst)
    return dst


def binary_path() -> Path:
    env = os.environ.get("WEBAUTHN_WORKER_BINARY")
    if env:
        return Path(env)
    candidate = APP_ROOT / "target" / "release" / "webauthn-assertion-worker"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    raise FileNotFoundError("webauthn-assertion-worker binary not found")


def run_worker(
    database: Path,
    output: Path,
    as_of: str = AS_OF,
    *,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(binary_path()),
        "--database",
        str(database.resolve()),
        "--as-of",
        as_of,
        "--output",
        str(output.resolve()),
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def query_one(db: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def query_rows(db: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db)
    try:
        return list(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assertion_by_id(report: dict[str, Any], assertion_id: str) -> dict[str, Any]:
    for row in report["assertion_rows"]:
        if row["assertion_id"] == assertion_id:
            return row
    raise KeyError(assertion_id)


def credential_by_id(report: dict[str, Any], credential_id: str) -> dict[str, Any]:
    for row in report["credential_rows"]:
        if row["credential_id"] == credential_id:
            return row
    raise KeyError(credential_id)


def challenge_by_id(report: dict[str, Any], challenge_id: str) -> dict[str, Any]:
    for row in report["challenge_rows"]:
        if row["challenge_id"] == challenge_id:
            return row
    raise KeyError(challenge_id)


def update_job(
    db: Path,
    assertion_id: str,
    *,
    client_data_json: bytes | None = None,
    authenticator_data: bytes | None = None,
    signature_der: bytes | None = None,
    credential_id: str | None = None,
    challenge_id: str | None = None,
    received_at: str | None = None,
    event_seq: int | None = None,
    status: str | None = None,
) -> None:
    conn = sqlite3.connect(db)
    try:
        fields: list[str] = []
        vals: list[Any] = []
        mapping = {
            "client_data_json": client_data_json,
            "authenticator_data": authenticator_data,
            "signature_der": signature_der,
            "credential_id": credential_id,
            "challenge_id": challenge_id,
            "received_at": received_at,
            "event_seq": event_seq,
            "status": status,
        }
        for col, val in mapping.items():
            if val is not None:
                fields.append(f"{col}=?")
                vals.append(val)
        if not fields:
            return
        vals.append(assertion_id)
        conn.execute(
            f"UPDATE assertion_jobs SET {', '.join(fields)} WHERE assertion_id=?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def insert_pending_job(
    db: Path,
    *,
    assertion_id: str,
    received_at: str,
    event_seq: int,
    credential_id: str,
    challenge_id: str,
    client_data_json: bytes,
    authenticator_data: bytes,
    signature_der: bytes,
) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """INSERT INTO assertion_jobs
               (assertion_id, received_at, event_seq, credential_id, challenge_id,
                client_data_json, authenticator_data, signature_der, status)
               VALUES (?,?,?,?,?,?,?,?, 'pending')""",
            (
                assertion_id,
                received_at,
                event_seq,
                credential_id,
                challenge_id,
                client_data_json,
                authenticator_data,
                signature_der,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_challenge(
    db: Path,
    *,
    challenge_id: str,
    rp_id: str,
    challenge_bytes: bytes,
    issued_at: str,
    expires_at: str,
    consumed_at: str | None = None,
    consumed_by: str | None = None,
) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """INSERT INTO challenges VALUES (?,?,?,?,?,?,?)""",
            (
                challenge_id,
                rp_id,
                challenge_bytes,
                issued_at,
                expires_at,
                consumed_at,
                consumed_by,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mutate_schema_version(db: Path, version: int) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE schema_metadata SET schema_version=?", (version,))
        conn.commit()
    finally:
        conn.close()


def snapshot_table(db: Path, table: str) -> list[tuple[Any, ...]]:
    return query_rows(db, f"SELECT * FROM {table} ORDER BY rowid")


def json_diff(a: Any, b: Any, path: str = "$") -> list[str]:
    diffs: list[str] = []

    def walk(x: Any, y: Any, p: str) -> None:
        if len(diffs) >= 8:
            return
        if type(x) is not type(y) and not (
            isinstance(x, (int, float)) and isinstance(y, (int, float))
        ):
            diffs.append(f"{p}: type {type(x).__name__} != {type(y).__name__}")
            return
        if isinstance(x, dict):
            keys = sorted(set(x) | set(y))
            for k in keys:
                if k not in x:
                    diffs.append(f"{p}.{k}: missing in left")
                elif k not in y:
                    diffs.append(f"{p}.{k}: missing in right")
                else:
                    walk(x[k], y[k], f"{p}.{k}")
                if len(diffs) >= 8:
                    return
        elif isinstance(x, list):
            if len(x) != len(y):
                diffs.append(f"{p}: len {len(x)} != {len(y)}")
                return
            for i, (xi, yi) in enumerate(zip(x, y, strict=True)):
                walk(xi, yi, f"{p}[{i}]")
                if len(diffs) >= 8:
                    return
        else:
            if x != y:
                diffs.append(f"{p}: {x!r} != {y!r}")

    walk(a, b, path)
    return diffs


def pretty_report_bytes(obj: dict[str, Any]) -> bytes:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    return text.encode("utf-8")


def reinsert_shuffled(db: Path, seed: int) -> None:
    """Reorder physical rows while preserving semantic keys/values."""
    import random

    rng = random.Random(seed)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        for table in (
            "assertion_results",
            "assertion_jobs",
            "challenges",
            "credentials",
            "rp_origins",
            "users",
            "rp_policies",
        ):
            rows = list(conn.execute(f"SELECT * FROM {table}").fetchall())
            cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            rng.shuffle(rows)
            conn.execute(f"DELETE FROM {table}")
            placeholders = ",".join("?" * len(cols))
            col_list = ",".join(cols)
            conn.executemany(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                rows,
            )
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()
    finally:
        conn.close()
