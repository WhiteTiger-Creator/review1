"""Behavioral verifier for recover-online-schema-swap-with-reader-pins."""

from __future__ import annotations

import json
import socket
import sqlite3
from pathlib import Path

import pytest
from db_factory import (
    AUDIT_FIELDS,
    FAILPOINT_EXIT,
    STATUS_FIELDS,
    active_upgrade_id,
    build_legacy_v1_db,
    build_legacy_v2_db,
    build_malformed_legacy_db,
    build_unsupported_legacy_db,
    committed_nonce_keys,
    database_mutable_paths,
    encrypt_payload_via_put,
    file_digest_map,
    get_payload,
    http_json,
    init_db,
    init_empty_db,
    journal_source_target,
    logical_payloads_via_generations,
    make_malformed_journal_db,
    read_canonical_occurrences,
    read_catalog_snapshot,
    read_journal_snapshot,
    read_nonce_reservations,
    read_records_snapshot,
    read_reservations_snapshot,
    reader_get_payload,
    reader_open_json,
    recover_one_partial_copy,
    recover_twice,
    recover_until_complete_through_partial_copy,
    restart_opsd,
    run_opsctl,
    run_upgrade_with_failpoint,
    set_batch_size,
    set_copy_cursor,
    start_opsd,
    status_json,
    stop_opsd,
    validate_reservation_row_correspondence,
    wait_for_http,
)
from model import (
    LogicalRecord,
    RecordVersion,
    expected_logical_state,
    expected_logical_state_after_writes,
    expected_published_generation_after_rotations,
    expected_published_generation_after_upgrade,
    expected_source_occurrence_count,
    generations_required_for_pins_and_journal,
)

FAILPOINTS = [
    "after-reservation",
    "after-partial-copy",
    "after-copy-complete",
    "after-target-validation",
    "after-publication",
    "after-pin-reconciliation",
    "during-cleanup",
]


def _source_records() -> list[LogicalRecord]:
    return [
        LogicalRecord("cred-alpha", "alpha-payload", RecordVersion(0, 1)),
        LogicalRecord("cred-beta", "beta-payload", RecordVersion(0, 1)),
        LogicalRecord("cred-gamma", "gamma-payload", RecordVersion(0, 1)),
        LogicalRecord("cred-delta", "delta-payload", RecordVersion(0, 1)),
        LogicalRecord("cred-epsilon", "epsilon-payload", RecordVersion(0, 1)),
    ]


def _published_gen(status: dict) -> int:
    pub = status.get("published_generation")
    if isinstance(pub, dict):
        return int(pub["0"])
    if isinstance(pub, list):
        return int(pub[0])
    return int(pub)


def _assert_status_schema(status: dict) -> None:
    for key in STATUS_FIELDS:
        assert key in status, f"missing status field {key}"
    assert "phase" not in status
    assert "generation_id" not in status
    assert "reader_count" not in status


def _ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_uninterrupted_upgrade_matches_logical_model(tmp_path):
    """An uninterrupted upgrade publishes the next generation with the same logical records."""
    db, cfg = init_db(tmp_path, batch_size=3)
    run_opsctl(db, cfg, "upgrade")
    status = status_json(db, cfg)
    assert status["upgrade_phase"] in {"complete", "Complete", "idle", "Idle"}
    pub = _published_gen(status)
    assert pub == expected_published_generation_after_upgrade()
    expected = expected_logical_state(_source_records())
    actual = logical_payloads_via_generations(db, cfg, pub)
    assert actual == {k: v.payload for k, v in expected.items()}


@pytest.mark.parametrize("failpoint", FAILPOINTS)
def test_each_documented_rotation_barrier_converges(tmp_path, failpoint: str):
    """Every documented failpoint recovers to the same logical state as an uninterrupted upgrade."""
    db, cfg = init_db(tmp_path, batch_size=3)
    proc = run_upgrade_with_failpoint(db, cfg, failpoint)
    if failpoint == "during-cleanup":
        run_opsctl(db, cfg, "upgrade")
        proc = run_opsctl(db, cfg, "cleanup", env={"KSEAL_FAILPOINT": failpoint}, allow_fail=True)
    assert proc.returncode in {0, FAILPOINT_EXIT}
    recover_twice(db, cfg)
    pub = _published_gen(status_json(db, cfg))
    expected = expected_logical_state(_source_records())
    actual = logical_payloads_via_generations(db, cfg, pub)
    assert actual == {k: v.payload for k, v in expected.items()}


def test_partial_batch_recovery_never_reuses_nonce_key_pair(tmp_path):
    """Partial-copy recovery must not reuse a committed nonce pair within a generation."""
    db, cfg = init_db(tmp_path, batch_size=2)
    proc = run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    assert proc.returncode == FAILPOINT_EXIT
    recover_twice(db, cfg)
    keys = committed_nonce_keys(db)
    assert len(keys) == len(set(keys)), (
        "committed (key_id, nonce) pairs must be unique within each generation"
    )


def test_new_readers_never_observe_mixed_generation(tmp_path):
    """New readers must read every record from the published generation only."""
    db, cfg = init_db(tmp_path, batch_size=2)
    proc = run_upgrade_with_failpoint(db, cfg, "after-publication")
    assert proc.returncode == FAILPOINT_EXIT
    recover_twice(db, cfg)
    pub = _published_gen(status_json(db, cfg))
    expected = logical_payloads_via_generations(db, cfg, pub)
    for record_id in expected:
        assert get_payload(db, cfg, record_id) == expected[record_id]


def test_existing_reader_snapshot_survives_restart_and_retirement(tmp_path):
    """Durable reader tokens keep the pinned generation across recovery and cleanup."""
    db, cfg = init_db(tmp_path, batch_size=3)
    snap = reader_open_json(db, cfg)
    token = snap["token"]
    pinned_gen = snap["generation_id"]
    original = reader_get_payload(db, cfg, token, "cred-alpha")
    proc = run_upgrade_with_failpoint(db, cfg, "after-publication")
    assert proc.returncode == FAILPOINT_EXIT
    recover_twice(db, cfg)
    run_opsctl(db, cfg, "cleanup")
    after = reader_get_payload(db, cfg, token, "cred-alpha")
    assert after == original
    conn = sqlite3.connect(db)
    try:
        exists = conn.execute(
            "SELECT COUNT(*) FROM generation_catalog WHERE generation_id = ?",
            (pinned_gen,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert exists == 1


def test_multi_snapshot_retention_across_generations(tmp_path):
    """Cleanup removes only generations without active durable snapshots."""
    db, cfg = init_db(tmp_path, batch_size=3)
    first = reader_open_json(db, cfg)
    run_opsctl(db, cfg, "upgrade")
    second = reader_open_json(db, cfg)
    run_opsctl(db, cfg, "reader-close", first["token"])
    run_opsctl(db, cfg, "cleanup")
    conn = sqlite3.connect(db)
    try:
        gens = {row[0] for row in conn.execute("SELECT generation_id FROM generation_catalog").fetchall()}
    finally:
        conn.close()
    assert first["generation_id"] not in gens or first["generation_id"] == second["generation_id"]
    assert second["generation_id"] in gens


def test_invalid_resume_is_database_immutable(tmp_path):
    """Malformed resume input is rejected without mutating database or audit files."""
    db, cfg = make_malformed_journal_db(tmp_path)
    audit = tmp_path / "store.audit.jsonl"
    paths = [db, audit, Path(str(db) + "-wal"), Path(str(db) + "-shm")]
    before = file_digest_map(paths)
    proc = run_opsctl(db, cfg, "recover", allow_fail=True)
    assert proc.returncode != 0
    after = file_digest_map(paths)
    assert before == after


def test_resume_order_is_idempotent(tmp_path):
    """Repeated recover and cleanup sequences converge without changing logical state."""
    db, cfg = init_db(tmp_path, batch_size=2)
    run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    recover_twice(db, cfg)
    pub = _published_gen(status_json(db, cfg))
    baseline = logical_payloads_via_generations(db, cfg, pub)
    run_opsctl(db, cfg, "recover")
    run_opsctl(db, cfg, "cleanup")
    run_opsctl(db, cfg, "recover")
    status = status_json(db, cfg)
    pub = _published_gen(status)
    final = logical_payloads_via_generations(db, cfg, pub)
    assert final == baseline


def test_ordinary_reads_writes_and_api_schema_are_preserved(tmp_path):
    """CLI put/get and status keep the documented response field set."""
    db, cfg = init_db(tmp_path, records=[("api-cred", "plain")], batch_size=3)
    proc = run_opsctl(db, cfg, "put", "cli-cred", "cli-value")
    assert proc.returncode == 0
    payload = get_payload(db, cfg, "cli-cred")
    assert payload == "cli-value"
    status = status_json(db, cfg)
    assert json.loads(json.dumps(status))
    _assert_status_schema(status)


def test_generated_scenarios_match_independent_model(tmp_path):
    """Seeded generated cases match the independent logical model after upgrade recovery."""
    seeds = [0xA17E2026, 0xBADC0FFE, 0x51A7E000]
    for seed in seeds:
        records = []
        for i in range(3 + (seed % 3)):
            rid = f"gen-{seed % 10000}-{i}"
            records.append((rid, f"payload-{seed}-{i}"))
        db, cfg = init_db(tmp_path / str(seed), records=records, batch_size=2 + (seed % 2))
        run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
        recover_twice(db, cfg)
        pub = _published_gen(status_json(db, cfg))
        logical = [
            LogicalRecord(rid, payload, RecordVersion(0, 1)) for rid, payload in records
        ]
        expected = expected_logical_state(logical)
        actual = logical_payloads_via_generations(db, cfg, pub)
        assert actual == {k: v.payload for k, v in expected.items()}


def test_status_and_audit_remain_structurally_compatible(tmp_path):
    """Status JSON and audit JSONL retain required operator fields."""
    db, cfg = init_db(tmp_path)
    run_opsctl(db, cfg, "upgrade")
    status = status_json(db, cfg)
    _assert_status_schema(status)
    assert isinstance(status["generation_states"], list)
    assert status["upgrade_phase"] in {"complete", "Complete", "idle", "Idle"}
    audit_path = tmp_path / "store.audit.jsonl"
    assert audit_path.exists()
    line = audit_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    entry = json.loads(line)
    for key in AUDIT_FIELDS:
        assert key in entry


def test_nonce_uniqueness_after_uninterrupted_upgrade(tmp_path):
    """A clean upgrade keeps committed nonce pairs unique within each generation."""
    db, cfg = init_db(tmp_path, batch_size=3)
    run_opsctl(db, cfg, "upgrade")
    keys = committed_nonce_keys(db)
    assert len(keys) == len(set(keys)), (
        "committed (key_id, nonce) pairs must be unique within each generation"
    )


def test_published_reads_do_not_fall_back_to_older_generations(tmp_path):
    """Current reads must reject records that exist only in an older generation."""
    db, cfg = init_db(tmp_path, records=[("shared", "published-value")], batch_size=2)
    run_opsctl(db, cfg, "upgrade")
    pub = _published_gen(status_json(db, cfg))
    assert pub == 2
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            """
            SELECT key_id, nonce, ciphertext, version_epoch, version_counter
            FROM records WHERE record_id = 'shared' AND generation_id = 1
            ORDER BY version_epoch DESC, version_counter DESC LIMIT 1
            """
        ).fetchone()
        assert row is not None
        # Leave published generation intact; plant an orphan only in the older generation.
        conn.execute(
            """
            INSERT INTO records
            (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
            VALUES ('orphan-only', 1, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()
    finally:
        conn.close()
    proc = run_opsctl(db, cfg, "get", "orphan-only", "--json", allow_fail=True)
    assert proc.returncode != 0
    assert get_payload(db, cfg, "shared") == "published-value"


def test_invalid_copied_target_is_not_published_by_recovery(tmp_path):
    """Recovery must fail validation on a corrupted copy without publishing the target."""
    db, cfg = init_db(tmp_path, batch_size=2)
    proc = run_upgrade_with_failpoint(db, cfg, "after-copy-complete")
    assert proc.returncode == FAILPOINT_EXIT
    before = status_json(db, cfg)
    published_before = _published_gen(before)
    conn = sqlite3.connect(db)
    try:
        target = conn.execute(
            "SELECT target_generation_id FROM upgrade_journal ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()[0]
        deleted = conn.execute(
            "DELETE FROM records WHERE generation_id = ? AND record_id = 'cred-alpha'",
            (target,),
        ).rowcount
        assert deleted == 1
        conn.commit()
        journal_before = conn.execute(
            "SELECT upgrade_id, phase, source_generation_id, target_generation_id, copy_cursor, reservation_batch FROM upgrade_journal"
        ).fetchall()
        catalog_before = conn.execute(
            "SELECT generation_id, state FROM generation_catalog ORDER BY generation_id"
        ).fetchall()
    finally:
        conn.close()

    recover = run_opsctl(db, cfg, "recover", allow_fail=True)
    assert recover.returncode != 0
    after = status_json(db, cfg)
    assert _published_gen(after) == published_before
    conn = sqlite3.connect(db)
    try:
        journal_after = conn.execute(
            "SELECT upgrade_id, phase, source_generation_id, target_generation_id, copy_cursor, reservation_batch FROM upgrade_journal"
        ).fetchall()
        catalog_after = conn.execute(
            "SELECT generation_id, state FROM generation_catalog ORDER BY generation_id"
        ).fetchall()
        target_state = conn.execute(
            "SELECT state FROM generation_catalog WHERE generation_id = ?",
            (target,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert journal_after == journal_before
    assert catalog_after == catalog_before
    assert target_state != "published"
    missing = run_opsctl(db, cfg, "get", "cred-alpha", "--json", allow_fail=True)
    # Prior published generation remains authoritative and still has the record.
    assert missing.returncode == 0


def test_cleanup_retains_journal_dependent_generation(tmp_path):
    """Cleanup must retain generations referenced by an unfinished upgrade journal."""
    db, cfg = init_db(tmp_path, batch_size=2)
    proc = run_upgrade_with_failpoint(db, cfg, "after-copy-complete")
    assert proc.returncode == FAILPOINT_EXIT
    conn = sqlite3.connect(db)
    try:
        source, target = conn.execute(
            "SELECT source_generation_id, target_generation_id FROM upgrade_journal ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        conn.execute(
            "UPDATE generation_catalog SET state = 'complete' WHERE generation_id = ?",
            (source,),
        )
        conn.commit()
    finally:
        conn.close()
    run_opsctl(db, cfg, "cleanup")
    conn = sqlite3.connect(db)
    try:
        gens = {
            row[0]
            for row in conn.execute("SELECT generation_id FROM generation_catalog").fetchall()
        }
    finally:
        conn.close()
    assert source in gens
    assert target in gens


def _legacy_rows_for_payloads(tmp_path: Path, payloads: list[tuple[str, str, int, int]]):
    rows = []
    for idx, (record_id, payload, epoch, counter) in enumerate(payloads):
        key_id, nonce, ciphertext, _, _ = encrypt_payload_via_put(
            tmp_path / f"cipher-{idx}",
            f"seed-{idx}",
            payload,
        )
        rows.append((record_id, key_id, nonce, ciphertext, epoch, counter))
    return rows


@pytest.mark.parametrize("target_mode", ["fresh", "initialized_empty"])
@pytest.mark.parametrize("legacy_version", [1, 2])
def test_legacy_import_into_fresh_or_empty_target(tmp_path, target_mode: str, legacy_version: int):
    """Legacy v1/v2 import succeeds for fresh and initialized-empty current-schema targets."""
    rows = _legacy_rows_for_payloads(
        tmp_path,
        [
            ("legacy-a", "payload-a", 0, 1),
            ("legacy-b", "payload-b", 0, 2),
        ],
    )
    source = tmp_path / f"legacy-v{legacy_version}.db"
    if legacy_version == 1:
        build_legacy_v1_db(source, rows)
    else:
        build_legacy_v2_db(source, rows)

    if target_mode == "fresh":
        db = tmp_path / "target.db"
        cfg = (tmp_path / "service.toml")
        from db_factory import write_config

        cfg = write_config(tmp_path, db, batch_size=3)
    else:
        db, cfg = init_empty_db(tmp_path / "empty")

    proc = run_opsctl(db, cfg, "import-legacy", "--source", str(source))
    assert proc.returncode == 0
    assert get_payload(db, cfg, "legacy-a") == "payload-a"
    assert get_payload(db, cfg, "legacy-b") == "payload-b"


@pytest.mark.parametrize("insertion_order", ["old_first", "new_first"])
def test_legacy_v1_selects_lexicographic_newest_version(tmp_path, insertion_order: str):
    """Import prefers (1,1) over (0,5) regardless of source row insertion order."""
    older = encrypt_payload_via_put(tmp_path / "old", "seed-old", "counter-wins-wrong")
    newer = encrypt_payload_via_put(tmp_path / "new", "seed-new", "epoch-wins-correct")
    old_row = ("r1", older[0], older[1], older[2], 0, 5)
    new_row = ("r1", newer[0], newer[1], newer[2], 1, 1)
    ordered = [old_row, new_row] if insertion_order == "old_first" else [new_row, old_row]
    source = tmp_path / "legacy-order.db"
    build_legacy_v1_db(source, ordered)
    db, cfg = init_empty_db(tmp_path / "target")
    run_opsctl(db, cfg, "import-legacy", "--source", str(source))
    assert get_payload(db, cfg, "r1") == "epoch-wins-correct"


def test_legacy_unsupported_version_leaves_target_immutable(tmp_path):
    """Unsupported legacy schema versions are rejected without mutating the target."""
    source = tmp_path / "legacy-unsupported.db"
    build_unsupported_legacy_db(source)
    db, cfg = init_empty_db(tmp_path / "target")
    audit = tmp_path / "target" / "store.audit.jsonl"
    before = file_digest_map([db, audit])
    proc = run_opsctl(db, cfg, "import-legacy", "--source", str(source), allow_fail=True)
    assert proc.returncode != 0
    after = file_digest_map([db, audit])
    assert before == after


def test_legacy_malformed_schema_leaves_target_immutable(tmp_path):
    """Malformed legacy sources are rejected without partially modifying the target."""
    source = tmp_path / "legacy-malformed.db"
    build_malformed_legacy_db(source)
    db, cfg = init_empty_db(tmp_path / "target")
    before = file_digest_map([db])
    proc = run_opsctl(db, cfg, "import-legacy", "--source", str(source), allow_fail=True)
    assert proc.returncode != 0
    after = file_digest_map([db])
    assert before == after


def test_legacy_rejects_non_empty_target_atomically(tmp_path):
    """Import into a non-empty target is rejected and leaves existing rows intact."""
    rows = _legacy_rows_for_payloads(tmp_path, [("incoming", "new-payload", 0, 1)])
    source = tmp_path / "legacy-nonempty.db"
    build_legacy_v1_db(source, rows)
    db, cfg = init_db(tmp_path / "target", records=[("existing", "keep-me")], batch_size=2)
    before = file_digest_map([db])
    proc = run_opsctl(db, cfg, "import-legacy", "--source", str(source), allow_fail=True)
    assert proc.returncode != 0
    after = file_digest_map([db])
    assert before == after
    assert get_payload(db, cfg, "existing") == "keep-me"


def test_http_api_lifecycle_survives_daemon_restart(tmp_path):
    """Real opsd HTTP lifecycle covers documented endpoints across restart and cleanup."""
    _, cfg = init_db(tmp_path, records=[], batch_size=2)
    port = _ephemeral_port()
    listen = f"127.0.0.1:{port}"
    base = f"http://{listen}"
    proc = start_opsd(cfg, listen)
    try:
        wait_for_http(f"{base}/v1/status")

        code, body = http_json("POST", f"{base}/v1/records", {"payload": "initial-value"})
        assert code == 200
        record_id = body["record_id"]

        code, reader = http_json("POST", f"{base}/v1/readers")
        assert code == 200
        token = reader["token"]

        code, pinned = http_json("GET", f"{base}/v1/readers/{token}/records/{record_id}")
        assert code == 200
        assert pinned["payload"] == "initial-value"

        code, _ = http_json("POST", f"{base}/v1/upgrade/start")
        assert code == 200

        code, _ = http_json("POST", f"{base}/v1/records", {"payload": "newer-value"})
        assert code == 200

        stop_opsd(proc)
        proc = start_opsd(cfg, listen)
        wait_for_http(f"{base}/v1/status")

        code, pinned_after = http_json("GET", f"{base}/v1/readers/{token}/records/{record_id}")
        assert code == 200
        assert pinned_after["payload"] == "initial-value"

        code, current = http_json("GET", f"{base}/v1/records/{record_id}")
        assert code == 200
        assert current["payload"] == "newer-value"

        code, status = http_json("GET", f"{base}/v1/status")
        assert code == 200
        _assert_status_schema(status)

        code, _ = http_json("DELETE", f"{base}/v1/readers/{token}")
        assert code == 200
        code, _ = http_json("POST", f"{base}/v1/upgrade/cleanup")
        assert code == 200

        code, err = http_json("GET", f"{base}/v1/records/missing-record-xyz")
        assert code == 400
        assert "error" in err and "code" in err
        assert err["code"] == "not_found"

        code, _ = http_json("POST", f"{base}/v1/upgrade/recover")
        assert code == 200
    finally:
        stop_opsd(proc)


def _records_for_count(count: int, prefix: str = "cred") -> list[tuple[str, str]]:
    return [(f"{prefix}-{i}", f"payload-{i}") for i in range(count)]


def _logical_from_tuples(records: list[tuple[str, str]]) -> list[LogicalRecord]:
    return [
        LogicalRecord(rid, payload, RecordVersion(0, 1)) for rid, payload in records
    ]


def test_repeated_partial_copy_crashes_cross_multiple_nonce_batches(tmp_path):
    """Repeated one-occurrence recoveries across many nonce batches converge like a clean upgrade."""
    record_count = 9
    batch_size = 2
    records = _records_for_count(record_count)
    db, cfg = init_db(tmp_path, records=records, batch_size=batch_size)
    expected = expected_logical_state(_logical_from_tuples(records))

    proc = run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    assert proc.returncode == FAILPOINT_EXIT

    iterations = recover_until_complete_through_partial_copy(db, cfg)
    assert iterations >= record_count

    status = status_json(db, cfg)
    pub = _published_gen(status)
    assert pub == expected_published_generation_after_upgrade()
    assert status["upgrade_phase"] in {"complete", "Complete", "idle", "Idle"}

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            """
            SELECT upgrade_id, source_generation_id, target_generation_id
            FROM upgrade_journal ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
        upgrade_id = str(row[0])
        source = int(row[1])
        target = int(row[2])
        source_occ = read_canonical_occurrences(db, source)
        target_occ = read_canonical_occurrences(db, target)
        batches = {
            batch
            for (batch,) in conn.execute(
                "SELECT DISTINCT batch_number FROM nonce_reservations WHERE upgrade_id = ?",
                (upgrade_id,),
            ).fetchall()
        }
    finally:
        conn.close()
    assert len(source_occ) == expected_source_occurrence_count(_logical_from_tuples(records))
    assert len(target_occ) == len(source_occ)
    assert {(r, e, c) for r, e, c, *_ in target_occ} == {(r, e, c) for r, e, c, *_ in source_occ}

    actual = logical_payloads_via_generations(db, cfg, pub)
    assert actual == {k: v.payload for k, v in expected.items()}

    keys = committed_nonce_keys(db)
    assert len(keys) == len(set(keys))

    assert len(batches) >= 5, "upgrade must cross multiple reservation batches"

    validate_reservation_row_correspondence(db, upgrade_id, target)

    baseline = logical_payloads_via_generations(db, cfg, pub)
    run_opsctl(db, cfg, "recover")
    run_opsctl(db, cfg, "cleanup")
    after = logical_payloads_via_generations(db, cfg, _published_gen(status_json(db, cfg)))
    assert after == baseline


def test_lagging_cursor_preserves_committed_target_row_and_reservation(tmp_path):
    """Recovery must not re-encrypt or re-reserve when the cursor lags behind committed work."""
    records = _records_for_count(5)
    db, cfg = init_db(tmp_path, records=records, batch_size=2)
    expected = expected_logical_state(_logical_from_tuples(records))

    proc = run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    assert proc.returncode == FAILPOINT_EXIT

    _, target = journal_source_target(db)
    target_occ = read_canonical_occurrences(db, target)
    assert len(target_occ) >= 1
    committed = target_occ[0]
    record_id, epoch, counter, key_id, nonce, ciphertext = committed

    upgrade_id = active_upgrade_id(db)
    reservations = read_nonce_reservations(db, upgrade_id)
    consumed = [r for r in reservations if r[5] == 1 and r[4] == record_id]
    assert len(consumed) == 1
    res_batch, res_slot, _, _, _, _ = consumed[0]
    identity = {
        "record_id": record_id,
        "version_epoch": epoch,
        "version_counter": counter,
        "key_id": key_id,
        "nonce": nonce,
        "ciphertext": ciphertext,
        "reservation_batch": res_batch,
        "reservation_slot": res_slot,
    }

    set_copy_cursor(db, upgrade_id, 0)

    recover_twice(db, cfg)
    pub = _published_gen(status_json(db, cfg))
    assert pub == expected_published_generation_after_upgrade()

    after_occ = read_canonical_occurrences(db, target)
    matching = [
        row for row in after_occ
        if row[0] == identity["record_id"]
        and row[1] == identity["version_epoch"]
        and row[2] == identity["version_counter"]
    ]
    assert len(matching) == 1
    _, _, _, after_key, after_nonce, after_ct = matching[0]
    assert after_key == identity["key_id"]
    assert after_nonce == identity["nonce"]
    assert after_ct == identity["ciphertext"]

    after_res = read_nonce_reservations(db, upgrade_id)
    naming = [
        r for r in after_res
        if r[5] == 1 and r[4] == record_id
    ]
    assert len(naming) == 1
    assert naming[0][0] == identity["reservation_batch"]
    assert naming[0][1] == identity["reservation_slot"]

    actual = logical_payloads_via_generations(db, cfg, pub)
    assert actual == {k: v.payload for k, v in expected.items()}

    keys = committed_nonce_keys(db)
    assert len(keys) == len(set(keys))

    baseline = logical_payloads_via_generations(db, cfg, pub)
    run_opsctl(db, cfg, "recover")
    assert logical_payloads_via_generations(db, cfg, pub) == baseline


@pytest.mark.parametrize(
    "corruption_kind",
    [
        "duplicate_nonce",
        "wrong_reservation_record",
        "row_reservation_mismatch",
        "orphaned_reservation",
        "cursor_skips_occurrence",
    ],
)
def test_malformed_target_reservation_accounting_is_rejected_atomically(
    tmp_path, corruption_kind: str
):
    """Malformed reservation or copy state is rejected without mutating durable files."""
    records = _records_for_count(5)
    db, cfg = init_db(tmp_path, records=records, batch_size=2)
    proc = run_upgrade_with_failpoint(db, cfg, "after-copy-complete")
    assert proc.returncode == FAILPOINT_EXIT

    source, target = journal_source_target(db)
    upgrade_id = active_upgrade_id(db)
    audit = tmp_path / "store.audit.jsonl"
    paths = database_mutable_paths(db, audit)

    conn = sqlite3.connect(db)
    try:
        if corruption_kind == "duplicate_nonce":
            rows = conn.execute(
                """
                SELECT record_id, key_id, nonce FROM records
                WHERE generation_id = ? ORDER BY record_id LIMIT 2
                """,
                (target,),
            ).fetchall()
            dup_key, dup_nonce = rows[0][1], rows[0][2]
            victim = rows[1][0]
            conn.execute(
                "UPDATE records SET key_id = ?, nonce = ? WHERE generation_id = ? AND record_id = ?",
                (dup_key, dup_nonce, target, victim),
            )
        elif corruption_kind == "wrong_reservation_record":
            conn.execute(
                """
                UPDATE nonce_reservations SET record_id = 'nonexistent-record'
                WHERE upgrade_id = ? AND consumed = 1 LIMIT 1
                """,
                (upgrade_id,),
            )
        elif corruption_kind == "row_reservation_mismatch":
            conn.execute(
                """
                UPDATE nonce_reservations SET nonce = 'mismatched-nonce-value'
                WHERE upgrade_id = ? AND consumed = 1 LIMIT 1
                """,
                (upgrade_id,),
            )
        elif corruption_kind == "orphaned_reservation":
            conn.execute(
                """
                UPDATE nonce_reservations SET record_id = 'orphan-only-row'
                WHERE upgrade_id = ? AND consumed = 1 LIMIT 1
                """,
                (upgrade_id,),
            )
        elif corruption_kind == "cursor_skips_occurrence":
            first = conn.execute(
                """
                SELECT record_id, version_epoch, version_counter FROM records
                WHERE generation_id = ? ORDER BY record_id, version_epoch, version_counter LIMIT 1
                """,
                (source,),
            ).fetchone()
            conn.execute(
                """
                DELETE FROM records
                WHERE generation_id = ? AND record_id = ? AND version_epoch = ? AND version_counter = ?
                """,
                (target, first[0], first[1], first[2]),
            )
            conn.execute(
                "UPDATE upgrade_journal SET copy_cursor = copy_cursor + 1 WHERE upgrade_id = ?",
                (upgrade_id,),
            )
        conn.commit()
    finally:
        conn.close()

    before_digests = file_digest_map(paths)
    journal_before = read_journal_snapshot(db)
    catalog_before = read_catalog_snapshot(db)
    records_before = read_records_snapshot(db)
    reservations_before = read_reservations_snapshot(db)
    published_before = _published_gen(status_json(db, cfg))

    proc = run_opsctl(db, cfg, "recover", allow_fail=True)
    assert proc.returncode != 0

    assert file_digest_map(paths) == before_digests
    assert read_journal_snapshot(db) == journal_before
    assert read_catalog_snapshot(db) == catalog_before
    assert read_records_snapshot(db) == records_before
    assert read_reservations_snapshot(db) == reservations_before
    assert _published_gen(status_json(db, cfg)) == published_before

    conn = sqlite3.connect(db)
    try:
        target_state = conn.execute(
            "SELECT state FROM generation_catalog WHERE generation_id = ?",
            (target,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert target_state != "published"
    assert get_payload(db, cfg, records[0][0]) == records[0][1]


def test_final_short_nonce_batch_allows_unused_capacity(tmp_path):
    """A final short reservation batch with unused slots still validates and publishes."""
    batch_size = 2
    record_count = 7
    records = _records_for_count(record_count)
    db, cfg = init_db(tmp_path, records=records, batch_size=batch_size)
    expected = expected_logical_state(_logical_from_tuples(records))

    proc = run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    assert proc.returncode == FAILPOINT_EXIT
    recover_until_complete_through_partial_copy(db, cfg, max_iterations=32)
    recover_twice(db, cfg)

    status = status_json(db, cfg)
    pub = _published_gen(status)
    assert pub == expected_published_generation_after_upgrade()

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            """
            SELECT upgrade_id, target_generation_id FROM upgrade_journal
            ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
        upgrade_id = str(row[0])
        target = int(row[1])
    finally:
        conn.close()

    validate_reservation_row_correspondence(db, upgrade_id, target)
    reservations = read_nonce_reservations(db, upgrade_id)
    unused = [r for r in reservations if r[5] == 0]
    if unused:
        for _, _, _, _, record_id, _ in unused:
            assert record_id is None

    keys = committed_nonce_keys(db)
    assert len(keys) == len(set(keys))

    actual = logical_payloads_via_generations(db, cfg, pub)
    assert actual == {k: v.payload for k, v in expected.items()}

    baseline = dict(actual)
    run_opsctl(db, cfg, "recover")
    run_opsctl(db, cfg, "cleanup")
    run_opsctl(db, cfg, "recover")
    assert logical_payloads_via_generations(db, cfg, _published_gen(status_json(db, cfg))) == baseline


def test_successive_recovered_rotations_preserve_each_reader_generation(tmp_path):
    """Two recovered rotations with pinned readers and intervening writes stay generation-isolated."""
    initial_records = _records_for_count(7)
    db, cfg = init_db(tmp_path, records=initial_records, batch_size=2)

    reader_a = reader_open_json(db, cfg)
    gen_a = reader_a["generation_id"]

    run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    recover_until_complete_through_partial_copy(db, cfg)
    recover_twice(db, cfg)

    reader_b = reader_open_json(db, cfg)
    gen_b = reader_b["generation_id"]
    assert gen_b == expected_published_generation_after_rotations(1)

    run_opsctl(db, cfg, "put", "cred-0", "updated-after-rotation-1")
    run_opsctl(db, cfg, "put", "new-after-rotation-1", "brand-new-value")

    base_logical = _logical_from_tuples(initial_records)
    expected_gen2 = expected_logical_state_after_writes(
        list(base_logical),
        [LogicalRecord("cred-0", "updated-after-rotation-1", RecordVersion(0, 2))],
        [LogicalRecord("new-after-rotation-1", "brand-new-value", RecordVersion(0, 1))],
    )

    set_batch_size(cfg, 3)

    run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
    recover_one_partial_copy(db, cfg)
    recover_one_partial_copy(db, cfg)
    recover_twice(db, cfg)

    port = _ephemeral_port()
    listen = f"127.0.0.1:{port}"
    proc = restart_opsd(cfg, listen)
    try:
        wait_for_http(f"http://{listen}/v1/status")
    finally:
        stop_opsd(proc)

    gen_c = expected_published_generation_after_rotations(2)
    status = status_json(db, cfg)
    assert _published_gen(status) == gen_c

    snap_a = {rid: reader_get_payload(db, cfg, reader_a["token"], rid) for rid, _ in initial_records}
    snap_b_records = list(initial_records) + [("new-after-rotation-1", "brand-new-value")]
    snap_b = {
        rid: reader_get_payload(db, cfg, reader_b["token"], rid)
        for rid, _ in snap_b_records
        if rid != "cred-0"
    }
    snap_b["cred-0"] = reader_get_payload(db, cfg, reader_b["token"], "cred-0")

    current = {
        rid: get_payload(db, cfg, rid)
        for rid in expected_gen2
    }
    assert current == {k: v.payload for k, v in expected_gen2.items()}

    for rid, payload in initial_records:
        assert reader_get_payload(db, cfg, reader_a["token"], rid) == snap_a[rid]
    assert reader_get_payload(db, cfg, reader_b["token"], "cred-0") == "updated-after-rotation-1"
    assert reader_get_payload(db, cfg, reader_b["token"], "new-after-rotation-1") == "brand-new-value"

    new_reader = reader_open_json(db, cfg)
    assert new_reader["generation_id"] == gen_c
    for rid in expected_gen2:
        assert reader_get_payload(db, cfg, new_reader["token"], rid) == expected_gen2[rid].payload

    conn = sqlite3.connect(db)
    try:
        catalog_gens = {
            row[0] for row in conn.execute("SELECT generation_id FROM generation_catalog").fetchall()
        }
        pin_gens = {
            int(row[0])
            for row in conn.execute(
                "SELECT generation_id FROM reader_pins WHERE released = 0"
            ).fetchall()
        }
    finally:
        conn.close()

    required = generations_required_for_pins_and_journal(
        pin_gens,
        {gen_a, gen_b, gen_c},
        gen_c,
        catalog_gens,
    )
    run_opsctl(db, cfg, "cleanup")
    conn = sqlite3.connect(db)
    try:
        after_cleanup = {
            row[0] for row in conn.execute("SELECT generation_id FROM generation_catalog").fetchall()
        }
    finally:
        conn.close()
    for gen in required:
        if gen in pin_gens or gen == gen_c:
            assert gen in after_cleanup

    keys = committed_nonce_keys(db)
    gen_keys = [k for k in keys if k[0] in {gen_b, gen_c}]
    assert len(gen_keys) == len(set(gen_keys))

    run_opsctl(db, cfg, "reader-close", reader_a["token"])
    run_opsctl(db, cfg, "cleanup")
    assert reader_get_payload(db, cfg, reader_b["token"], "cred-0") == "updated-after-rotation-1"

    run_opsctl(db, cfg, "reader-close", reader_b["token"])
    run_opsctl(db, cfg, "cleanup")

    run_opsctl(db, cfg, "recover")
    run_opsctl(db, cfg, "cleanup")
    final = logical_payloads_via_generations(db, cfg, gen_c)
    assert final == {k: v.payload for k, v in expected_gen2.items()}


def test_generated_multi_batch_recovery_matrix(tmp_path):
    """Deterministic batch/record matrix cases recover to the independent logical model."""
    matrix = [
        (1, 4),
        (2, 7),
        (3, 10),
        (4, 13),
    ]
    for batch_size, record_count in matrix:
        records = _records_for_count(record_count, prefix=f"b{batch_size}")
        case_dir = tmp_path / f"bs{batch_size}-rc{record_count}"
        db, cfg = init_db(case_dir, records=records, batch_size=batch_size)
        expected = expected_logical_state(_logical_from_tuples(records))

        run_upgrade_with_failpoint(db, cfg, "after-partial-copy")
        extra_failures = batch_size % 3
        for _ in range(extra_failures):
            proc = recover_one_partial_copy(db, cfg)
            assert proc.returncode == FAILPOINT_EXIT
        recover_twice(db, cfg)

        pub = _published_gen(status_json(db, cfg))
        actual = logical_payloads_via_generations(db, cfg, pub)
        assert actual == {k: v.payload for k, v in expected.items()}

        target = pub
        conn = sqlite3.connect(db)
        try:
            upgrade_id = conn.execute(
                "SELECT upgrade_id FROM upgrade_journal ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()[0]
            phase = conn.execute(
                "SELECT phase FROM upgrade_journal WHERE upgrade_id = ?",
                (upgrade_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        assert phase in {"complete", "idle"}

        validate_reservation_row_correspondence(db, str(upgrade_id), target)
        keys = committed_nonce_keys(db)
        assert len(keys) == len(set(keys))

        baseline = dict(actual)
        run_opsctl(db, cfg, "recover")
        assert logical_payloads_via_generations(db, cfg, pub) == baseline
