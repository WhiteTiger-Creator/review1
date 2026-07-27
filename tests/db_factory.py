"""Verifier-owned database construction helpers."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

APP = Path("/app")
BIN = Path("/app/bin/opsctl")
OPSD = Path("/app/bin/opsd")
FAILPOINT_EXIT = 75

DEFAULT_RECORDS = [
    ("cred-alpha", "alpha-payload"),
    ("cred-beta", "beta-payload"),
    ("cred-gamma", "gamma-payload"),
    ("cred-delta", "delta-payload"),
    ("cred-epsilon", "epsilon-payload"),
]

STATUS_FIELDS = (
    "database_path",
    "schema_version",
    "current_generation",
    "published_generation",
    "upgrade_phase",
    "upgrade_id",
    "active_reader_count",
    "generation_states",
)

AUDIT_FIELDS = (
    "timestamp",
    "operation",
    "upgrade_id",
    "phase",
    "outcome",
    "source_generation",
    "target_generation",
    "reader_count",
    "reason_code",
)


def write_config(tmp_dir: Path, db_path: Path, batch_size: int = 3) -> Path:
    cfg = tmp_dir / "service.toml"
    cfg.write_text(
        "\n".join(
            [
                f'database_path = "{db_path}"',
                f'audit_path = "{tmp_dir / "store.audit.jsonl"}"',
                f"batch_size = {batch_size}",
                'active_key_id = "key-current"',
                "supported_legacy_versions = [1, 2]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cfg


def run_opsctl(
    db_path: Path,
    config_path: Path,
    *args: str,
    env: dict | None = None,
    allow_fail: bool = False,
) -> subprocess.CompletedProcess[str]:
    proc_env = {
        "PATH": "/usr/local/bin:/usr/local/cargo/bin:/app/bin:/usr/bin:/bin",
        "KSEAL_CONFIG": str(config_path),
        **(env or {}),
    }
    proc = subprocess.run(
        [str(BIN), "--db", str(db_path), *args],
        capture_output=True,
        text=True,
        env=proc_env,
        check=False,
    )
    if not allow_fail and proc.returncode != 0:
        raise AssertionError(
            f"opsctl failed ({proc.returncode}): {proc.stderr}\n{proc.stdout}"
        )
    return proc


def init_db(
    tmp_dir: Path,
    records: list[tuple[str, str]] | None = None,
    batch_size: int = 3,
) -> tuple[Path, Path]:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_dir / "store.db"
    cfg = write_config(tmp_dir, db_path, batch_size=batch_size)
    run_opsctl(db_path, cfg, "init")
    seed = DEFAULT_RECORDS if records is None else records
    for record_id, payload in seed:
        run_opsctl(db_path, cfg, "put", record_id, payload)
    return db_path, cfg


def init_empty_db(tmp_dir: Path, batch_size: int = 3) -> tuple[Path, Path]:
    """Initialize a current-schema database with no credential rows."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_dir / "store.db"
    cfg = write_config(tmp_dir, db_path, batch_size=batch_size)
    run_opsctl(db_path, cfg, "init")
    return db_path, cfg


def run_upgrade_with_failpoint(
    db_path: Path,
    cfg: Path,
    failpoint: str | None,
) -> subprocess.CompletedProcess[str]:
    env = {"KSEAL_FAILPOINT": failpoint} if failpoint else {}
    return run_opsctl(
        db_path,
        cfg,
        "upgrade",
        env=env,
        allow_fail=True,
    )


def recover_twice(db_path: Path, cfg: Path) -> None:
    run_opsctl(db_path, cfg, "recover")
    run_opsctl(db_path, cfg, "recover")


def reader_open_json(db_path: Path, cfg: Path) -> dict:
    proc = run_opsctl(db_path, cfg, "reader-open", "--json")
    return json.loads(proc.stdout)


def reader_get_payload(db_path: Path, cfg: Path, token: str, record_id: str) -> str:
    proc = run_opsctl(db_path, cfg, "reader-get", token, record_id, "--json")
    return json.loads(proc.stdout)["payload"]


def get_payload(db_path: Path, cfg: Path, record_id: str) -> str:
    proc = run_opsctl(db_path, cfg, "get", record_id, "--json")
    return json.loads(proc.stdout)["payload"]


def status_json(db_path: Path, cfg: Path) -> dict:
    proc = run_opsctl(db_path, cfg, "status", "--json")
    return json.loads(proc.stdout)


def committed_nonce_keys(
    db_path: Path,
) -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT generation_id, key_id, nonce
            FROM records
            ORDER BY generation_id, record_id, version_epoch, version_counter
            """
        ).fetchall()
    finally:
        conn.close()
    return [(int(generation_id), str(key_id), str(nonce)) for generation_id, key_id, nonce in rows]


def generation_record_payloads(db_path: Path, generation_id: int) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT record_id, ciphertext, key_id, nonce, version_epoch, version_counter
            FROM records WHERE generation_id = ?
            ORDER BY record_id, version_epoch, version_counter
            """,
            (generation_id,),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, str] = {}
    for record_id, _, key_id, nonce, epoch, counter in rows:
        out[record_id] = f"{epoch}:{counter}:{key_id}:{nonce}"
    return out


def logical_payloads_via_generations(db_path: Path, cfg: Path, generation_id: int) -> dict[str, str]:
    """Return record_id -> payload for rows in a generation using reader pin trick."""
    token_proc = run_opsctl(db_path, cfg, "reader-open", "--json")
    token = json.loads(token_proc.stdout)["token"]
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE reader_pins SET generation_id = ? WHERE token = ?",
            (generation_id, token),
        )
        conn.commit()
        record_ids = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT record_id FROM records WHERE generation_id = ?",
                (generation_id,),
            ).fetchall()
        ]
    finally:
        conn.close()
    payloads = {}
    for rid in record_ids:
        payloads[rid] = reader_get_payload(db_path, cfg, token, rid)
    run_opsctl(db_path, cfg, "reader-close", token)
    return payloads


def file_digest_map(paths: list[Path]) -> dict[str, str]:
    import hashlib

    out: dict[str, str] = {}
    for path in paths:
        if path.exists():
            out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def make_malformed_journal_db(tmp_dir: Path) -> tuple[Path, Path]:
    db_path, cfg = init_db(tmp_dir, records=[("only-one", "payload")], batch_size=2)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO upgrade_journal
            (upgrade_id, phase, source_generation_id, target_generation_id, copy_cursor, reservation_batch, last_action, updated_at)
            VALUES ('bad-upgrade', 'copying', 1, 99, 0, 0, 'begin', datetime('now'))
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path, cfg


def encrypt_payload_via_put(tmp_dir: Path, record_id: str, payload: str) -> tuple[str, str, bytes, int, int]:
    """Create ciphertext through the deployed implementation, then read raw row fields."""
    db, cfg = init_db(tmp_dir, records=[], batch_size=3)
    run_opsctl(db, cfg, "put", record_id, payload)
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            """
            SELECT key_id, nonce, ciphertext, version_epoch, version_counter
            FROM records WHERE record_id = ? ORDER BY version_epoch DESC, version_counter DESC LIMIT 1
            """,
            (record_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return str(row[0]), str(row[1]), bytes(row[2]), int(row[3]), int(row[4])


def build_legacy_v1_db(
    path: Path,
    rows: list[tuple[str, str, str, bytes, int, int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        conn.execute(
            """
            CREATE TABLE legacy_records (
                record_id TEXT NOT NULL,
                key_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                version_epoch INTEGER NOT NULL,
                version_counter INTEGER NOT NULL,
                PRIMARY KEY (record_id, version_epoch, version_counter)
            )
            """
        )
        for record_id, key_id, nonce, ciphertext, epoch, counter in rows:
            conn.execute(
                """
                INSERT INTO legacy_records
                (record_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, key_id, nonce, ciphertext, epoch, counter),
            )
        conn.commit()
    finally:
        conn.close()


def build_legacy_v2_db(
    path: Path,
    rows: list[tuple[str, str, str, bytes, int, int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES ('schema_version', '2')")
        conn.execute(
            """
            CREATE TABLE records (
                record_id TEXT NOT NULL,
                generation_id INTEGER NOT NULL,
                key_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                version_epoch INTEGER NOT NULL DEFAULT 0,
                version_counter INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (record_id, generation_id, version_epoch, version_counter)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE generation_catalog (
                generation_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                key_id TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO generation_catalog VALUES (1, 'published', 'key-current', 2, datetime('now'))"
        )
        for record_id, key_id, nonce, ciphertext, epoch, counter in rows:
            conn.execute(
                """
                INSERT INTO records
                (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (record_id, key_id, nonce, ciphertext, epoch, counter),
            )
        conn.commit()
    finally:
        conn.close()


def build_unsupported_legacy_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES ('schema_version', '9')")
        conn.execute(
            "CREATE TABLE legacy_records (record_id TEXT, key_id TEXT, nonce TEXT, ciphertext BLOB, version_epoch INTEGER, version_counter INTEGER)"
        )
        conn.commit()
    finally:
        conn.close()


def build_malformed_legacy_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        # Intentionally omit legacy_records table.
        conn.commit()
    finally:
        conn.close()


def wait_for_http(url: str, timeout_sec: float = 15.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_sec
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001 - readiness polling
            last_err = exc
            time.sleep(0.1)
    raise AssertionError(f"HTTP endpoint not ready: {url} last_error={last_err}")


def http_json(
    method: str,
    url: str,
    body: dict | None = None,
) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}
        return exc.code, parsed


def start_opsd(cfg: Path, listen: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [str(OPSD), "--listen", listen, "--config", str(cfg)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            "PATH": "/usr/local/bin:/usr/local/cargo/bin:/app/bin:/usr/bin:/bin",
            "KSEAL_CONFIG": str(cfg),
        },
    )


def stop_opsd(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def set_batch_size(cfg: Path, batch_size: int) -> None:
    """Update only the test config batch_size in place."""
    text = cfg.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("batch_size ="):
            lines.append(f"batch_size = {batch_size}")
        else:
            lines.append(line)
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")


def database_mutable_paths(db_path: Path, audit_path: Path | None = None) -> list[Path]:
    paths = [db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")]
    if audit_path is not None:
        paths.append(audit_path)
    return paths


def read_canonical_occurrences(
    db_path: Path,
    generation_id: int,
) -> list[tuple[str, int, int, str, str, bytes]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT record_id, version_epoch, version_counter, key_id, nonce, ciphertext
            FROM records WHERE generation_id = ?
            ORDER BY record_id, version_epoch, version_counter
            """,
            (generation_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        (str(rid), int(epoch), int(counter), str(key_id), str(nonce), bytes(ct))
        for rid, epoch, counter, key_id, nonce, ct in rows
    ]


def read_nonce_reservations(
    db_path: Path,
    upgrade_id: str,
) -> list[tuple[int, int, str, str, str | None, int]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT batch_number, slot, key_id, nonce, record_id, consumed
            FROM nonce_reservations
            WHERE upgrade_id = ?
            ORDER BY batch_number, slot
            """,
            (upgrade_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        (
            int(batch),
            int(slot),
            str(key_id),
            str(nonce),
            str(record_id) if record_id is not None else None,
            int(consumed),
        )
        for batch, slot, key_id, nonce, record_id, consumed in rows
    ]


def read_journal_snapshot(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT upgrade_id, phase, source_generation_id, target_generation_id,
                   copy_cursor, reservation_batch
            FROM upgrade_journal ORDER BY updated_at
            """
        ).fetchall()
    finally:
        conn.close()


def read_catalog_snapshot(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT generation_id, state FROM generation_catalog ORDER BY generation_id"
        ).fetchall()
    finally:
        conn.close()


def read_records_snapshot(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT record_id, generation_id, key_id, nonce, ciphertext,
                   version_epoch, version_counter
            FROM records ORDER BY generation_id, record_id, version_epoch, version_counter
            """
        ).fetchall()
    finally:
        conn.close()


def read_reservations_snapshot(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT upgrade_id, batch_number, slot, key_id, nonce, record_id, consumed
            FROM nonce_reservations ORDER BY upgrade_id, batch_number, slot
            """
        ).fetchall()
    finally:
        conn.close()


def active_upgrade_id(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT upgrade_id FROM upgrade_journal
            WHERE phase NOT IN ('complete')
            ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return str(row[0])


def journal_source_target(db_path: Path) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT source_generation_id, target_generation_id
            FROM upgrade_journal WHERE phase NOT IN ('complete')
            ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row[0]), int(row[1])


def set_copy_cursor(db_path: Path, upgrade_id: str, cursor: int) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE upgrade_journal SET copy_cursor = ? WHERE upgrade_id = ?",
            (cursor, upgrade_id),
        )
        conn.commit()
    finally:
        conn.close()


def validate_reservation_row_correspondence(
    db_path: Path,
    upgrade_id: str,
    target_generation: int,
) -> None:
    """Assert one-to-one correspondence between committed rows and consumed reservations."""
    occurrences = read_canonical_occurrences(db_path, target_generation)
    reservations = read_nonce_reservations(db_path, upgrade_id)
    consumed = [r for r in reservations if r[5] == 1]

    row_keys = {
        (rid, key_id, nonce)
        for rid, _, _, key_id, nonce, _ in occurrences
    }
    res_keys = {
        (record_id, key_id, nonce)
        for _, _, key_id, nonce, record_id, _ in consumed
        if record_id is not None
    }
    assert row_keys == res_keys, "committed rows and consumed reservations must match exactly"
    assert len(consumed) == len(occurrences), "each committed row needs one consumed reservation"

    coord_set = {(batch, slot) for batch, slot, _, _, _, _ in consumed}
    assert len(coord_set) == len(consumed), "consumed reservation coordinates must be unique"

    for _, _, key_id, nonce, record_id, consumed_flag in reservations:
        if consumed_flag == 0:
            assert record_id is None, "unconsumed reservations must not name a committed record"


def recover_one_partial_copy(db_path: Path, cfg: Path) -> subprocess.CompletedProcess[str]:
    return run_opsctl(
        db_path,
        cfg,
        "recover",
        env={"KSEAL_FAILPOINT": "after-partial-copy"},
        allow_fail=True,
    )


def recover_until_complete_through_partial_copy(
    db_path: Path,
    cfg: Path,
    max_iterations: int = 64,
) -> int:
    """Repeatedly recover through after-partial-copy until one invocation completes."""
    iterations = 0
    while iterations < max_iterations:
        proc = recover_one_partial_copy(db_path, cfg)
        iterations += 1
        if proc.returncode == 0:
            return iterations
        assert proc.returncode == FAILPOINT_EXIT, proc.stderr
    raise AssertionError(f"recovery did not converge within {max_iterations} iterations")


def restart_opsd(cfg: Path, listen: str, proc: subprocess.Popen[str] | None = None) -> subprocess.Popen[str]:
    if proc is not None:
        stop_opsd(proc)
    return start_opsd(cfg, listen)


def rebuild_release() -> None:
    subprocess.run(
        ["cargo", "build", "--release", "--locked", "--offline"],
        cwd=APP,
        check=True,
        env={
            "PATH": "/usr/local/bin:/usr/local/cargo/bin:/app/bin:/usr/bin:/bin",
            "CARGO_NET_OFFLINE": "true",
            "HOME": str(Path.home()),
        },
    )
    shutil.copy(APP / "target/release/opsctl", APP / "bin/opsctl")
    shutil.copy(APP / "target/release/opsd", APP / "bin/opsd")
