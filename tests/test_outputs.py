"""Exactly 24 candidate-facing tests for the WebAuthn assertion ledger repair worker."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from helpers.wa_helpers import (
    AS_OF,
    TEST_DIR,
    assertion_by_id,
    auth_data,
    binary_path,
    challenge_by_id,
    client_data_bytes,
    copy_fixture_db,
    credential_by_id,
    insert_challenge,
    insert_pending_job,
    json_diff,
    load_private_key,
    load_report,
    mutate_schema_version,
    pretty_report_bytes,
    query_one,
    query_rows,
    reinsert_shuffled,
    run_worker,
    sign_assertion,
    snapshot_table,
    update_job,
)

UP = 0x01
UV = 0x04
BE = 0x08
BS = 0x10

PERMUTATION_SEEDS = (7, 19, 41, 83, 127)
GOLDEN_PATH = TEST_DIR / "fixtures" / "canonical_report.json"
GOLDEN_HASH_PATH = TEST_DIR / "fixtures" / "canonical_report.sha256"


def _run_cli(
    database: str | Path,
    output: str | Path,
    as_of: str = AS_OF,
    *,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(binary_path()),
        "--database",
        str(database),
        "--as-of",
        as_of,
        "--output",
        str(output),
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _output_path(tmp: Path) -> Path:
    out_dir = tmp / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "report.json"


def _run_on_copy(tmp: Path, db: Path | None = None):
    database = db or copy_fixture_db()
    output = _output_path(tmp)
    proc = run_worker(database, output, AS_OF)
    report = load_report(output) if output.is_file() else None
    return proc, output, report, database


def _job_row(db: Path, assertion_id: str) -> tuple[bytes, bytes, bytes]:
    row = query_rows(
        db,
        """SELECT client_data_json, authenticator_data, signature_der
           FROM assertion_jobs WHERE assertion_id=?""",
        (assertion_id,),
    )[0]
    return row[0], row[1], row[2]


def _credential_rp(db: Path, credential_id: str) -> str:
    return query_one(db, "SELECT rp_id FROM credentials WHERE credential_id=?", (credential_id,))


def _challenge_bytes(db: Path, challenge_id: str) -> bytes:
    return query_one(
        db, "SELECT challenge_bytes FROM challenges WHERE challenge_id=?", (challenge_id,)
    )


def _origin_for_rp(db: Path, rp_id: str) -> str:
    return query_one(db, "SELECT origin FROM rp_origins WHERE rp_id=? LIMIT 1", (rp_id,))


def _private_key_for_credential(credential_id: str):
    if credential_id == "cred-backup-b":
        return load_private_key("key_b.pem")
    return load_private_key("key_a.pem")


def _resign_job(
    db: Path,
    assertion_id: str,
    *,
    client_data_json: bytes | None = None,
    authenticator_data: bytes | None = None,
) -> None:
    cred_id = query_one(
        db, "SELECT credential_id FROM assertion_jobs WHERE assertion_id=?", (assertion_id,)
    )
    cdata, adata, _ = _job_row(db, assertion_id)
    if client_data_json is not None:
        cdata = client_data_json
    if authenticator_data is not None:
        adata = authenticator_data
    sk = _private_key_for_credential(cred_id)
    sig = sign_assertion(sk, adata, cdata)
    update_job(
        db, assertion_id, client_data_json=cdata, authenticator_data=adata, signature_der=sig
    )


def _insert_signed_job(
    db: Path,
    *,
    assertion_id: str,
    received_at: str,
    event_seq: int,
    credential_id: str,
    challenge_id: str,
    origin: str,
    flags: int,
    sign_count: int,
    extra_client: dict | None = None,
) -> None:
    rp_id = _credential_rp(db, credential_id)
    chal = _challenge_bytes(db, challenge_id)
    cdata = client_data_bytes(chal, origin, **(extra_client or {}))
    adata = auth_data(rp_id, flags, sign_count)
    sk = _private_key_for_credential(credential_id)
    sig = sign_assertion(sk, adata, cdata)
    insert_pending_job(
        db,
        assertion_id=assertion_id,
        received_at=received_at,
        event_seq=event_seq,
        credential_id=credential_id,
        challenge_id=challenge_id,
        client_data_json=cdata,
        authenticator_data=adata,
        signature_der=sig,
    )


def _db_fingerprint(db: Path) -> dict[str, list[tuple]]:
    tables = (
        "schema_metadata",
        "rp_policies",
        "rp_origins",
        "users",
        "credentials",
        "challenges",
        "assertion_jobs",
        "assertion_results",
    )
    return {t: snapshot_table(db, t) for t in tables}


def test_01_native_cli_schema_and_preflight_validation(tmp_path: Path) -> None:
    """Native binary requires absolute paths and validates schema before mutation."""
    assert binary_path().is_file() and os.access(binary_path(), os.X_OK)

    db = copy_fixture_db()
    out_parent = tmp_path / "parent"
    out_parent.mkdir()
    out = out_parent / "report.json"

    rel_db = _run_cli("relative/db.sqlite", out, AS_OF)
    assert rel_db.returncode != 0
    assert rel_db.stderr.strip()

    rel_out = _run_cli(db, "relative/out.json", AS_OF)
    assert rel_out.returncode != 0
    assert rel_out.stderr.strip()

    bad_as_of = _run_cli(db, out, "2026-07-01T12:00:00+00:00")
    assert bad_as_of.returncode != 0

    unknown_flag = _run_cli(db, out, AS_OF, extra_args=["--unexpected"])
    assert unknown_flag.returncode != 0
    assert unknown_flag.stderr.strip()

    assert query_one(db, "SELECT schema_version FROM schema_metadata") == 1
    for table in (
        "schema_metadata",
        "rp_policies",
        "rp_origins",
        "users",
        "credentials",
        "challenges",
        "assertion_jobs",
        "assertion_results",
    ):
        assert (
            query_one(
                db, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            == 1
        )

    proc, _, report, _ = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    assert report is not None
    assert report["summary"]["processed_assertion_count"] == 12


def test_02_fatal_database_state_rolls_back_and_cleans_output(tmp_path: Path) -> None:
    """Fatal database state rolls back mutations and cleans stale/temporary outputs."""
    db = copy_fixture_db()
    before = _db_fingerprint(db)
    out_parent = tmp_path / "out"
    out_parent.mkdir()
    out = out_parent / "report.json"
    out.write_text("stale report\n", encoding="utf-8")
    tmp = Path(str(out) + ".tmp")
    tmp.write_text("temporary\n", encoding="utf-8")

    mutate_schema_version(db, 2)
    before = _db_fingerprint(db)
    proc = run_worker(db, out, AS_OF)
    assert proc.returncode != 0
    assert proc.stderr.strip()
    assert not out.exists()
    assert not tmp.exists()
    assert _db_fingerprint(db) == before

    db2 = copy_fixture_db()
    conn = sqlite3.connect(db2)
    conn.execute(
        """INSERT INTO assertion_results
           (assertion_id, status, reason_or_null, risk_or_null, credential_id,
            challenge_id, received_at, user_present_or_null, user_verified_or_null,
            backup_eligible_or_null, backup_state_or_null, sign_count_or_null,
            sign_count_before_or_null, sign_count_after_or_null, challenge_consumed,
            credential_mutated)
           VALUES ('assert-zero-zero','rejected','invalid_signature',NULL,
                   'cred-device-a','chal-zero','2026-06-10T10:00:00Z',
                   NULL,NULL,NULL,NULL,NULL,0,0,0,0)"""
    )
    conn.commit()
    conn.close()
    before2 = _db_fingerprint(db2)
    out2 = out_parent / "report2.json"
    proc2 = run_worker(db2, out2, AS_OF)
    assert proc2.returncode != 0
    assert proc2.stderr.strip()
    assert not out2.exists()
    assert _db_fingerprint(db2) == before2


def test_03_chronological_processing_and_as_of_window(tmp_path: Path) -> None:
    """as_of window ignores future jobs; final report rows sort by received_at then assertion_id.

    Final report order is independent of processing order (received_at, event_seq,
    assertion_id). This test checks the as_of window and report presentation order
    only; it does not prove processing-order semantics.
    """
    proc, _, report, db = _run_on_copy(tmp_path)
    assert proc.returncode == 0
    rows = report["assertion_rows"]
    keys = [(r["received_at"], r["assertion_id"]) for r in rows]
    assert keys == sorted(keys)
    assert all(r["assertion_id"] != "assert-future" for r in rows)
    assert (
        query_one(db, "SELECT status FROM assertion_jobs WHERE assertion_id='assert-future'")
        == "pending"
    )
    assert (
        query_one(db, "SELECT COUNT(*) FROM assertion_results WHERE assertion_id='assert-future'")
        == 0
    )
    assert report["summary"]["pending_future_job_count"] == 1


def test_04_credential_identity_user_and_status_binding(tmp_path: Path) -> None:
    """Unknown, revoked, and disabled-user credentials reject without mutation."""
    db = copy_fixture_db()
    insert_challenge(
        db,
        challenge_id="chal-synth-unknown",
        rp_id="example.com",
        challenge_bytes=b"synth-chal-unknown!!",
        issued_at="2026-06-01T00:00:00Z",
        expires_at="2026-07-15T00:00:00Z",
    )
    insert_pending_job(
        db,
        assertion_id="assert-unknown-cred",
        received_at="2026-06-13T10:00:00Z",
        event_seq=900,
        credential_id="cred-missing",
        challenge_id="chal-synth-unknown",
        client_data_json=b"{}",
        authenticator_data=b"\x00" * 37,
        signature_der=b"\x30",
    )
    _insert_signed_job(
        db,
        assertion_id="assert-disabled-user",
        received_at="2026-06-13T11:00:00Z",
        event_seq=901,
        credential_id="cred-disabled-d",
        challenge_id="chal-revoked",
        origin="https://example.com",
        flags=UP,
        sign_count=2,
    )

    proc, _, report, _ = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0

    revoked = assertion_by_id(report, "assert-revoked")
    assert revoked["reason_or_null"] == "credential_inactive"
    assert revoked["challenge_consumed"] == 0
    assert revoked["credential_mutated"] == 0
    assert revoked["user_present_or_null"] is None

    unknown = assertion_by_id(report, "assert-unknown-cred")
    assert unknown["reason_or_null"] == "credential_unknown"
    assert unknown["challenge_consumed"] == 0

    disabled = assertion_by_id(report, "assert-disabled-user")
    assert disabled["reason_or_null"] == "credential_inactive"
    assert disabled["challenge_consumed"] == 0


def test_05_client_data_utf8_json_and_duplicate_member_handling(tmp_path: Path) -> None:
    """Malformed clientDataJSON rejects as client_data_malformed without consumption."""
    cases: list[tuple[str, bytes]] = [
        ("bad-utf8", b"\xffnot-json"),
        ("bad-json", b"{not json"),
        ("bad-top", b"[1,2,3]"),
        ("bad-type-field", b'{"type":1,"challenge":"x","origin":"https://example.com"}'),
        ("missing-origin", b'{"type":"webauthn.get","challenge":"abc"}'),
        (
            "dup-type",
            b'{"type":"webauthn.get","type":"webauthn.get","challenge":"abc","origin":"https://example.com"}',
        ),
        (
            "bad-cross",
            b'{"type":"webauthn.get","challenge":"abc","origin":"https://example.com","crossOrigin":"yes"}',
        ),
    ]
    for suffix, blob in cases:
        db = copy_fixture_db()
        update_job(db, "assert-badsig", client_data_json=blob)
        proc, _, report, _ = _run_on_copy(tmp_path / suffix, db)
        assert proc.returncode == 0
        row = assertion_by_id(report, "assert-badsig")
        assert row["reason_or_null"] == "client_data_malformed", suffix
        assert row["challenge_consumed"] == 0


def test_06_client_data_type_is_webauthn_get(tmp_path: Path) -> None:
    """Wrong ceremony type rejects as client_data_type_invalid before authentication boundary."""
    db = copy_fixture_db()
    cdata, adata, _ = _job_row(db, "assert-badsig")
    cobj = json.loads(cdata)
    cobj["type"] = "webauthn.create"
    new_cdata = json.dumps(cobj, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )
    _resign_job(db, "assert-badsig", client_data_json=new_cdata, authenticator_data=adata)

    proc, _, report, _ = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-badsig")
    assert row["reason_or_null"] == "client_data_type_invalid"
    assert row["challenge_consumed"] == 0
    ch = challenge_by_id(report, "chal-badsig")
    assert ch["status"] == "available"


def test_07_challenge_binding_lifetime_and_replay(tmp_path: Path) -> None:
    """Challenge unknown, timing, consumed, equality, and byte-mismatch cases follow precedence."""
    proc, _, report, _ = _run_on_copy(tmp_path)
    assert proc.returncode == 0

    consumed = assertion_by_id(report, "assert-consumed")
    assert consumed["reason_or_null"] == "challenge_already_consumed"
    assert consumed["challenge_consumed"] == 0

    expired = assertion_by_id(report, "assert-expired")
    assert expired["reason_or_null"] == "challenge_expired"
    assert expired["challenge_consumed"] == 0

    db = copy_fixture_db()
    insert_challenge(
        db,
        challenge_id="chal-not-yet",
        rp_id="secure.example",
        challenge_bytes=b"challenge-not-yet!!",
        issued_at="2026-06-15T00:00:00Z",
        expires_at="2026-07-15T00:00:00Z",
    )
    _insert_signed_job(
        db,
        assertion_id="assert-not-yet",
        received_at="2026-06-10T14:00:00Z",
        event_seq=850,
        credential_id="cred-backup-b",
        challenge_id="chal-not-yet",
        origin="https://secure.example",
        flags=UP | UV | BE,
        sign_count=21,
    )
    proc2, _, report2, _ = _run_on_copy(tmp_path / "not-yet", db)
    assert proc2.returncode == 0
    row = assertion_by_id(report2, "assert-not-yet")
    assert row["reason_or_null"] == "challenge_not_yet_valid"
    assert row["challenge_consumed"] == 0

    # Inclusive expiration: received_at == expires_at is valid through later gates.
    db_eq = copy_fixture_db()
    insert_challenge(
        db_eq,
        challenge_id="chal-eq-exp",
        rp_id="example.com",
        challenge_bytes=b"chal-equal-expires!",
        issued_at="2026-06-01T00:00:00Z",
        expires_at="2026-06-10T12:20:00Z",
    )
    _insert_signed_job(
        db_eq,
        assertion_id="assert-eq-expires",
        received_at="2026-06-10T12:20:00Z",
        event_seq=910,
        credential_id="cred-device-a",
        challenge_id="chal-eq-exp",
        origin="https://example.com",
        flags=UP,
        sign_count=7,
    )
    proc_eq, _, report_eq, _ = _run_on_copy(tmp_path / "eq-exp", db_eq)
    assert proc_eq.returncode == 0
    eq_row = assertion_by_id(report_eq, "assert-eq-expires")
    assert eq_row["reason_or_null"] != "challenge_expired"
    assert eq_row["status"] == "accepted"
    assert eq_row["challenge_consumed"] == 1

    db3 = copy_fixture_db()
    cdata, adata, _ = _job_row(db3, "assert-badsig")
    cobj = json.loads(cdata)
    cobj["challenge"] = "wrong-challenge-bytes"
    bad = json.dumps(cobj, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )
    _resign_job(db3, "assert-badsig", client_data_json=bad, authenticator_data=adata)
    proc3, _, report3, _ = _run_on_copy(tmp_path / "mismatch", db3)
    assert proc3.returncode == 0
    mismatch = assertion_by_id(report3, "assert-badsig")
    assert mismatch["reason_or_null"] == "challenge_mismatch"
    assert mismatch["challenge_consumed"] == 0

    db4 = copy_fixture_db()
    insert_pending_job(
        db4,
        assertion_id="assert-unknown-chal",
        received_at="2026-06-11T08:00:00Z",
        event_seq=902,
        credential_id="cred-backup-b",
        challenge_id="chal-does-not-exist",
        client_data_json=b"{}",
        authenticator_data=b"\x00" * 37,
        signature_der=b"\x30",
    )
    proc4, _, report4, _ = _run_on_copy(tmp_path / "unknown", db4)
    assert proc4.returncode == 0
    unknown = assertion_by_id(report4, "assert-unknown-chal")
    assert unknown["reason_or_null"] == "challenge_unknown"


def test_08_origin_and_cross_origin_policy(tmp_path: Path) -> None:
    """Exact allowed-origin matching is required; crossOrigin true rejects without consumption."""
    db = copy_fixture_db()
    cdata, adata, _ = _job_row(db, "assert-badsig")
    cobj = json.loads(cdata)
    cobj["origin"] = "https://evil.example.com"
    bad_origin = json.dumps(cobj, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )
    _resign_job(db, "assert-badsig", client_data_json=bad_origin, authenticator_data=adata)
    proc, _, report, db_after = _run_on_copy(tmp_path / "origin", db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-badsig")
    assert row["reason_or_null"] == "origin_mismatch"
    assert row["challenge_consumed"] == 0
    assert challenge_by_id(report, "chal-badsig")["status"] == "available"
    assert (
        query_one(
            db_after, "SELECT sign_count FROM credentials WHERE credential_id='cred-device-a'"
        )
        == 6
    )

    db2 = copy_fixture_db()
    cdata2, adata2, _ = _job_row(db2, "assert-badsig")
    cobj2 = json.loads(cdata2)
    cobj2["crossOrigin"] = True
    xo = json.dumps(cobj2, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )
    _resign_job(db2, "assert-badsig", client_data_json=xo, authenticator_data=adata2)
    proc2, _, report2, _ = _run_on_copy(tmp_path / "xo", db2)
    assert proc2.returncode == 0
    row2 = assertion_by_id(report2, "assert-badsig")
    assert row2["reason_or_null"] == "cross_origin_disallowed"
    assert row2["challenge_consumed"] == 0
    assert challenge_by_id(report2, "chal-badsig")["status"] == "available"


def test_09_authenticator_data_layout_and_flag_mask(tmp_path: Path) -> None:
    """Authenticator data must be 37 bytes with supported flags only."""
    db = copy_fixture_db()
    _, adata, _ = _job_row(db, "assert-badsig")
    short = adata[:30]
    _resign_job(db, "assert-badsig", authenticator_data=short)
    proc, _, report, _ = _run_on_copy(tmp_path / "short", db)
    assert proc.returncode == 0
    assert (
        assertion_by_id(report, "assert-badsig")["reason_or_null"] == "authenticator_data_malformed"
    )

    db2 = copy_fixture_db()
    _, adata2, _ = _job_row(db2, "assert-badsig")
    reserved = bytearray(adata2)
    reserved[32] |= 0x40  # AT
    _resign_job(db2, "assert-badsig", authenticator_data=bytes(reserved))
    proc2, _, report2, _ = _run_on_copy(tmp_path / "at", db2)
    assert proc2.returncode == 0
    assert (
        assertion_by_id(report2, "assert-badsig")["reason_or_null"]
        == "authenticator_data_malformed"
    )

    db3 = copy_fixture_db()
    _, adata3, _ = _job_row(db3, "assert-badsig")
    ed = bytearray(adata3)
    ed[32] |= 0x80  # ED
    _resign_job(db3, "assert-badsig", authenticator_data=bytes(ed))
    proc3, _, report3, _ = _run_on_copy(tmp_path / "ed", db3)
    assert proc3.returncode == 0
    assert (
        assertion_by_id(report3, "assert-badsig")["reason_or_null"]
        == "authenticator_data_malformed"
    )


def test_10_rp_id_hash_binding(tmp_path: Path) -> None:
    """RP ID hash mismatch rejects before challenge consumption."""
    db = copy_fixture_db()
    _, adata, _ = _job_row(db, "assert-badsig")
    bad = bytearray(adata)
    bad[0] ^= 0xFF
    _resign_job(db, "assert-badsig", authenticator_data=bytes(bad))
    proc, _, report, _ = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-badsig")
    assert row["reason_or_null"] == "rp_id_hash_mismatch"
    assert row["challenge_consumed"] == 0
    assert challenge_by_id(report, "chal-badsig")["status"] == "available"


def test_11_original_client_data_bytes_are_signed(tmp_path: Path) -> None:
    """Direct raw-byte hashing anchor: noncanonical whitespace/member-order assertion accepts."""
    db = copy_fixture_db()
    cdata, _, _ = _job_row(db, "assert-whitespace")
    assert b"\n" in cdata or b" " in cdata
    # Prove stored bytes differ from serde_json compact re-encoding.
    compact = json.dumps(json.loads(cdata), separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert cdata != compact

    proc, _, report, _ = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-whitespace")
    assert row["status"] == "accepted"
    assert row["reason_or_null"] is None
    assert row["sign_count_or_null"] == 6
    assert row["challenge_consumed"] == 1


def test_12_es256_der_signature_verification(tmp_path: Path) -> None:
    """ES256 accepts valid DER and rejects tampered/malformed encodings without consumption."""
    # Normalization-stable valid DER acceptance (independent of Test 11 and batch order).
    db_ok = copy_fixture_db()
    cdata_ok, adata_ok, _ = _job_row(db_ok, "assert-badsig")
    # Advance from the live pre-badsig chronological count (6) with a valid signature.
    adata_ok = auth_data("example.com", UP, 7)
    _resign_job(db_ok, "assert-badsig", client_data_json=cdata_ok, authenticator_data=adata_ok)
    proc_ok, _, report_ok, _ = _run_on_copy(tmp_path / "valid-der", db_ok)
    assert proc_ok.returncode == 0
    ok_row = assertion_by_id(report_ok, "assert-badsig")
    assert ok_row["status"] == "accepted"
    assert ok_row["reason_or_null"] is None
    assert ok_row["challenge_consumed"] == 1

    db = copy_fixture_db()
    cdata, adata, _ = _job_row(db, "assert-badsig")
    sk = _private_key_for_credential("cred-device-a")
    good_sig = sign_assertion(sk, adata, cdata)
    update_job(db, "assert-badsig", signature_der=good_sig)
    tampered = bytearray(adata)
    tampered[36] ^= 0x01
    update_job(db, "assert-badsig", authenticator_data=bytes(tampered))
    proc2, _, report2, db2 = _run_on_copy(tmp_path / "tamper", db)
    assert proc2.returncode == 0
    bad = assertion_by_id(report2, "assert-badsig")
    assert bad["reason_or_null"] == "invalid_signature"
    assert bad["challenge_consumed"] == 0
    assert bad["credential_mutated"] == 0
    assert challenge_by_id(report2, "chal-badsig")["status"] == "available"
    assert (
        query_one(db2, "SELECT sign_count FROM credentials WHERE credential_id='cred-device-a'")
        == 6
    )

    db3 = copy_fixture_db()
    update_job(db3, "assert-badsig", signature_der=b"\x30\x06\x02\x01\x00\x02\x01\x00")
    proc3, _, report3, _ = _run_on_copy(tmp_path / "malformed", db3)
    assert proc3.returncode == 0
    assert assertion_by_id(report3, "assert-badsig")["reason_or_null"] == "invalid_signature"
    assert assertion_by_id(report3, "assert-badsig")["challenge_consumed"] == 0

    db4 = copy_fixture_db()
    cdata4, adata4, _ = _job_row(db4, "assert-badsig")
    good4 = sign_assertion(sk, adata4, cdata4)
    r, s = decode_dss_signature(good4)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    update_job(db4, "assert-badsig", signature_der=raw)
    proc4, _, report4, _ = _run_on_copy(tmp_path / "raw", db4)
    assert proc4.returncode == 0
    assert assertion_by_id(report4, "assert-badsig")["reason_or_null"] == "invalid_signature"
    assert assertion_by_id(report4, "assert-badsig")["challenge_consumed"] == 0

    db5 = copy_fixture_db()
    cdata5, adata5, _ = _job_row(db5, "assert-badsig")
    good5 = sign_assertion(sk, adata5, cdata5)
    update_job(db5, "assert-badsig", signature_der=good5 + b"\x00")
    proc5, _, report5, _ = _run_on_copy(tmp_path / "trailing", db5)
    assert proc5.returncode == 0
    assert assertion_by_id(report5, "assert-badsig")["reason_or_null"] == "invalid_signature"
    assert assertion_by_id(report5, "assert-badsig")["challenge_consumed"] == 0


def test_13_user_presence_policy(tmp_path: Path) -> None:
    """Missing user presence rejects after authentication with challenge consumption only."""
    db = copy_fixture_db()
    cdata, adata, _ = _job_row(db, "assert-badsig")
    no_up = bytearray(adata)
    no_up[32] &= ~UP
    _resign_job(db, "assert-badsig", client_data_json=cdata, authenticator_data=bytes(no_up))
    proc, _, report, db_after = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-badsig")
    assert row["reason_or_null"] == "user_presence_required"
    assert row["challenge_consumed"] == 1
    assert row["credential_mutated"] == 0
    assert row["sign_count_before_or_null"] == 6
    assert row["sign_count_after_or_null"] == 6
    assert (
        query_one(
            db_after,
            "SELECT consumed_by_assertion_id FROM challenges WHERE challenge_id='chal-badsig'",
        )
        == "assert-badsig"
    )
    cred = credential_by_id(report, "cred-device-a")
    assert cred["sign_count"] == 6
    assert (
        query_one(db_after, "SELECT sign_count FROM credentials WHERE credential_id='cred-device-a'")
        == 6
    )
    assert (
        query_one(
            db_after, "SELECT backup_state FROM credentials WHERE credential_id='cred-device-a'"
        )
        == cred["backup_state"]
    )
    assert (
        query_one(
            db_after, "SELECT last_used_at FROM credentials WHERE credential_id='cred-device-a'"
        )
        == cred["last_used_at_or_null"]
    )


def test_14_user_verification_policy(tmp_path: Path) -> None:
    """UV-required RP rejects missing UV after authentication; later UV assertion accepts."""
    db = copy_fixture_db()
    # Isolate from earlier backup jobs that can quarantine under wrong ordering.
    conn = sqlite3.connect(db)
    for aid in ("assert-backup-risk", "assert-backup-bs"):
        conn.execute(
            "UPDATE assertion_jobs SET received_at='2026-07-02T01:00:00Z' WHERE assertion_id=?",
            (aid,),
        )
    conn.commit()
    conn.close()

    proc, _, report, db_after = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    miss = assertion_by_id(report, "assert-uv-miss")
    assert miss["reason_or_null"] == "user_verification_required"
    assert miss["challenge_consumed"] == 1
    assert miss["credential_mutated"] == 0
    assert miss["sign_count_before_or_null"] == 20
    assert miss["sign_count_after_or_null"] == 20
    assert (
        query_one(
            db_after,
            "SELECT consumed_by_assertion_id FROM challenges WHERE challenge_id='chal-uv-miss'",
        )
        == "assert-uv-miss"
    )

    ok = assertion_by_id(report, "assert-uv-ok")
    assert ok["status"] == "accepted"
    assert ok["user_verified_or_null"] == 1
    assert ok["sign_count_before_or_null"] == 20
    assert ok["sign_count_after_or_null"] == 30
    assert credential_by_id(report, "cred-backup-b")["sign_count"] == 30


def test_15_backup_flag_consistency(tmp_path: Path) -> None:
    """BS without BE rejects after authentication while consuming the challenge."""
    db = copy_fixture_db()
    cdata, adata, _ = _job_row(db, "assert-badsig")
    bad = bytearray(adata)
    bad[32] = UP | BS
    _resign_job(db, "assert-badsig", client_data_json=cdata, authenticator_data=bytes(bad))
    proc, _, report, db_after = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-badsig")
    assert row["reason_or_null"] == "backup_flags_invalid"
    assert row["challenge_consumed"] == 1
    assert row["credential_mutated"] == 0
    assert row["sign_count_before_or_null"] == 6
    assert row["sign_count_after_or_null"] == 6
    cred = credential_by_id(report, "cred-device-a")
    assert cred["backup_state"] == 0
    assert cred["sign_count"] == 6
    assert (
        query_one(db_after, "SELECT sign_count FROM credentials WHERE credential_id='cred-device-a'")
        == 6
    )
    assert (
        query_one(
            db_after, "SELECT backup_state FROM credentials WHERE credential_id='cred-device-a'"
        )
        == 0
    )
    assert (
        query_one(
            db_after, "SELECT last_used_at FROM credentials WHERE credential_id='cred-device-a'"
        )
        == cred["last_used_at_or_null"]
    )


def test_16_backup_eligibility_is_immutable(tmp_path: Path) -> None:
    """Incoming BE must match stored backup_eligible; mismatch consumes without mutation."""
    db = copy_fixture_db()
    cdata, adata, _ = _job_row(db, "assert-badsig")
    be_set = bytearray(adata)
    be_set[32] = UP | BE
    _resign_job(db, "assert-badsig", client_data_json=cdata, authenticator_data=bytes(be_set))
    proc, _, report, db_after = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0
    row = assertion_by_id(report, "assert-badsig")
    assert row["reason_or_null"] == "backup_eligibility_changed"
    assert row["challenge_consumed"] == 1
    assert row["credential_mutated"] == 0
    assert row["sign_count_before_or_null"] == 6
    assert row["sign_count_after_or_null"] == 6
    cred = credential_by_id(report, "cred-device-a")
    assert cred["backup_eligible"] == 0
    assert cred["backup_state"] == 0
    assert cred["sign_count"] == 6
    assert (
        query_one(db_after, "SELECT sign_count FROM credentials WHERE credential_id='cred-device-a'")
        == 6
    )
    assert (
        query_one(
            db_after, "SELECT backup_state FROM credentials WHERE credential_id='cred-device-a'"
        )
        == 0
    )
    assert (
        query_one(
            db_after, "SELECT last_used_at FROM credentials WHERE credential_id='cred-device-a'"
        )
        == cred["last_used_at_or_null"]
    )


def test_17_valid_signature_counter_advancement(tmp_path: Path) -> None:
    """Advancing counters accept, update credential state, and consume challenges."""
    proc, _, report, _ = _run_on_copy(tmp_path)
    assert proc.returncode == 0
    adv = assertion_by_id(report, "assert-zero-advance")
    assert adv["status"] == "accepted"
    assert adv["sign_count_before_or_null"] == 0
    assert adv["sign_count_after_or_null"] == 5
    assert adv["challenge_consumed"] == 1
    assert adv["credential_mutated"] == 1
    cred = credential_by_id(report, "cred-device-a")
    assert cred["sign_count"] == 6
    assert cred["last_used_at_or_null"] == "2026-06-10T12:00:00Z"


def test_18_zero_signature_counter_semantics(tmp_path: Path) -> None:
    """Stored and received zero counters mean unsupported counter, not replay risk."""
    proc, _, report, _ = _run_on_copy(tmp_path)
    assert proc.returncode == 0
    zero = assertion_by_id(report, "assert-zero-zero")
    assert zero["status"] == "accepted"
    assert zero["sign_count_or_null"] == 0
    assert zero["sign_count_before_or_null"] == 0
    assert zero["sign_count_after_or_null"] == 0
    assert zero["risk_or_null"] is None

    adv = assertion_by_id(report, "assert-zero-advance")
    assert adv["status"] == "accepted"
    assert adv["sign_count_before_or_null"] == 0
    assert adv["sign_count_after_or_null"] == 5


def test_19_single_device_counter_replay_quarantines(tmp_path: Path) -> None:
    """Strict non-increasing nonzero counters quarantine without changing sign_count."""
    proc, _, report, _ = _run_on_copy(tmp_path)
    assert proc.returncode == 0
    replay = assertion_by_id(report, "assert-replay")
    assert replay["reason_or_null"] == "signature_counter_replay"
    assert replay["challenge_consumed"] == 1
    assert replay["credential_mutated"] == 1
    assert replay["sign_count_before_or_null"] == 6
    assert replay["sign_count_after_or_null"] == 6
    cred = credential_by_id(report, "cred-device-a")
    assert cred["status"] == "quarantined"
    assert cred["sign_count"] == 6
    assert cred["last_used_at_or_null"] == "2026-06-10T12:00:00Z"


def test_20_backup_aware_nonmonotonic_counter_acceptance(tmp_path: Path) -> None:
    """Backup-aware accepts non-monotonic counters with risk; strict still quarantines."""
    proc, _, report, _ = _run_on_copy(tmp_path)
    assert proc.returncode == 0
    risk = assertion_by_id(report, "assert-backup-risk")
    assert risk["status"] == "accepted"
    assert risk["risk_or_null"] == "non_monotonic_backup_counter"
    assert risk["sign_count_before_or_null"] == 20
    assert risk["sign_count_after_or_null"] == 20
    cred_b = credential_by_id(report, "cred-backup-b")
    assert cred_b["status"] == "active"
    assert cred_b["sign_count"] == 30

    db = copy_fixture_db()
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE rp_policies SET backup_counter_policy='strict' WHERE rp_id='secure.example'"
    )
    conn.commit()
    conn.close()
    proc2, _, report2, _ = _run_on_copy(tmp_path / "strict", db)
    assert proc2.returncode == 0
    strict_row = assertion_by_id(report2, "assert-backup-risk")
    assert strict_row["reason_or_null"] == "signature_counter_replay"
    assert credential_by_id(report2, "cred-backup-b")["status"] == "quarantined"


def test_21_dynamic_signed_mutation_locality_and_atomicity(tmp_path: Path) -> None:
    """Three-job chronological interaction: advance, UV-consume, then challenge replay."""
    db = copy_fixture_db()
    # Isolate cred-backup-b from later canonical secure.example jobs.
    conn = sqlite3.connect(db)
    for aid in (
        "assert-backup-risk",
        "assert-backup-bs",
        "assert-uv-miss",
        "assert-uv-ok",
    ):
        conn.execute(
            "UPDATE assertion_jobs SET received_at='2026-07-02T01:00:00Z' WHERE assertion_id=?",
            (aid,),
        )
    conn.commit()
    conn.close()

    insert_challenge(
        db,
        challenge_id="chal-t21-a",
        rp_id="secure.example",
        challenge_bytes=b"t21-chal-A-bytes!!",
        issued_at="2026-06-01T00:00:00Z",
        expires_at="2026-07-15T00:00:00Z",
    )
    insert_challenge(
        db,
        challenge_id="chal-t21-b",
        rp_id="secure.example",
        challenge_bytes=b"t21-chal-B-bytes!!",
        issued_at="2026-06-01T00:00:00Z",
        expires_at="2026-07-15T00:00:00Z",
    )

    shared_received = "2026-06-11T08:00:00Z"
    # Lexicographic assertion_id order is reverse of event_seq order.
    # Physical insert order intentionally differs from event_seq order.
    _insert_signed_job(
        db,
        assertion_id="assert-t21-c",
        received_at=shared_received,
        event_seq=100,
        credential_id="cred-backup-b",
        challenge_id="chal-t21-a",
        origin="https://secure.example",
        flags=UP | UV | BE,
        sign_count=21,
    )
    _insert_signed_job(
        db,
        assertion_id="assert-t21-a",
        received_at=shared_received,
        event_seq=300,
        credential_id="cred-backup-b",
        challenge_id="chal-t21-b",
        origin="https://secure.example",
        flags=UP | UV | BE,
        sign_count=22,
    )
    _insert_signed_job(
        db,
        assertion_id="assert-t21-b",
        received_at=shared_received,
        event_seq=200,
        credential_id="cred-backup-b",
        challenge_id="chal-t21-b",
        origin="https://secure.example",
        flags=UP | BE,  # UV clear
        sign_count=22,
    )

    ids = ["assert-t21-a", "assert-t21-b", "assert-t21-c"]
    assert ids == sorted(ids)
    seqs = [
        query_one(db, "SELECT event_seq FROM assertion_jobs WHERE assertion_id=?", (i,))
        for i in ids
    ]
    assert seqs == [300, 200, 100]

    before_summary_pending = query_one(
        db, "SELECT COUNT(*) FROM assertion_jobs WHERE status='pending' AND received_at<=?", (AS_OF,)
    )

    proc, _, report, db_after = _run_on_copy(tmp_path, db)
    assert proc.returncode == 0

    step1 = assertion_by_id(report, "assert-t21-c")
    assert step1["status"] == "accepted"
    assert step1["risk_or_null"] is None
    assert step1["sign_count_before_or_null"] == 20
    assert step1["sign_count_after_or_null"] == 21
    assert step1["challenge_consumed"] == 1
    assert step1["credential_mutated"] == 1
    assert challenge_by_id(report, "chal-t21-a")["consumed_by_assertion_id_or_null"] == "assert-t21-c"

    step2 = assertion_by_id(report, "assert-t21-b")
    assert step2["reason_or_null"] == "user_verification_required"
    assert step2["sign_count_before_or_null"] == 21
    assert step2["sign_count_after_or_null"] == 21
    assert step2["challenge_consumed"] == 1
    assert step2["credential_mutated"] == 0
    assert challenge_by_id(report, "chal-t21-b")["consumed_by_assertion_id_or_null"] == "assert-t21-b"

    step3 = assertion_by_id(report, "assert-t21-a")
    assert step3["reason_or_null"] == "challenge_already_consumed"
    assert step3["sign_count_before_or_null"] == 21
    assert step3["sign_count_after_or_null"] == 21
    assert step3["challenge_consumed"] == 0
    assert step3["credential_mutated"] == 0

    cred = credential_by_id(report, "cred-backup-b")
    assert cred["sign_count"] == 21
    assert cred["status"] == "active"
    assert (
        query_one(db_after, "SELECT sign_count FROM credentials WHERE credential_id='cred-backup-b'")
        == 21
    )

    # Summary deltas implied by the three synthetic jobs among newly eligible work.
    assert report["summary"]["pending_future_job_count"] == 5  # future + 4 deferred secure jobs
    assert before_summary_pending >= 3


def test_22_five_seed_sqlite_insertion_order_invariance(tmp_path: Path) -> None:
    """Physical SQLite row order does not change semantic report output for five shuffle seeds."""
    proc0, _, baseline, _ = _run_on_copy(tmp_path / "baseline")
    assert proc0.returncode == 0

    for seed in PERMUTATION_SEEDS:
        db = copy_fixture_db()
        reinsert_shuffled(db, seed)
        proc, _, report, _ = _run_on_copy(tmp_path / f"seed-{seed}", db)
        assert proc.returncode == 0, seed
        if report != baseline:
            diffs = json_diff(baseline, report)
            pytest.fail(f"seed {seed} mismatch: {diffs}")


def test_23_one_strict_complete_parsed_report_comparison(tmp_path: Path) -> None:
    """Only complete comparison: verify golden SHA-256 then require strict equality."""
    golden_bytes = GOLDEN_PATH.read_bytes()
    expect_hash = GOLDEN_HASH_PATH.read_text(encoding="utf-8").strip().split()[0]
    assert hashlib.sha256(golden_bytes).hexdigest() == expect_hash
    golden = json.loads(golden_bytes.decode("utf-8"))

    proc, _, report, _ = _run_on_copy(tmp_path)
    assert proc.returncode == 0
    diffs = json_diff(golden, report)
    if diffs:
        pytest.fail("report mismatch; first diffs: " + json.dumps(diffs, indent=2))


def test_24_byte_identical_rerun_idempotence_and_batch_failure_cleanup(tmp_path: Path) -> None:
    """Reruns are byte-identical; fatal batch failures roll back and clean outputs."""
    db = copy_fixture_db()
    out_parent = tmp_path / "idem"
    out_parent.mkdir()
    out = out_parent / "report.json"

    proc1 = run_worker(db, out, AS_OF)
    assert proc1.returncode == 0
    bytes1 = out.read_bytes()

    db2 = copy_fixture_db()
    proc2 = run_worker(db2, out_parent / "report2.json", AS_OF)
    assert proc2.returncode == 0
    bytes2 = (out_parent / "report2.json").read_bytes()
    assert bytes1 == bytes2
    assert bytes1.endswith(b"\n")
    assert b"  " in bytes1
    assert not bytes1.endswith(b" \n")

    report1 = json.loads(bytes1.decode("utf-8"))
    assert bytes1 == pretty_report_bytes(report1)

    summary = report1["summary"]
    rows = report1["assertion_rows"]
    assert summary["processed_assertion_count"] == len(rows)
    assert summary["accepted_assertion_count"] == sum(1 for r in rows if r["status"] == "accepted")
    assert summary["rejected_assertion_count"] == sum(1 for r in rows if r["status"] == "rejected")
    assert summary["risk_assertion_count"] == sum(1 for r in rows if r["risk_or_null"] is not None)

    fatal_db = copy_fixture_db()
    fatal_out_parent = tmp_path / "fatal-out"
    fatal_out_parent.mkdir()
    fatal_out = fatal_out_parent / "report.json"
    fatal_out.write_text("stale\n", encoding="utf-8")
    Path(str(fatal_out) + ".tmp").write_text("tmp\n", encoding="utf-8")
    conn = sqlite3.connect(fatal_db)
    conn.execute(
        """INSERT INTO assertion_results
           (assertion_id, status, reason_or_null, risk_or_null, credential_id,
            challenge_id, received_at, user_present_or_null, user_verified_or_null,
            backup_eligible_or_null, backup_state_or_null, sign_count_or_null,
            sign_count_before_or_null, sign_count_after_or_null, challenge_consumed,
            credential_mutated)
           VALUES ('assert-zero-zero','rejected','invalid_signature',NULL,
                   'cred-device-a','chal-zero','2026-06-10T10:00:00Z',
                   NULL,NULL,NULL,NULL,NULL,0,0,0,0)"""
    )
    conn.commit()
    conn.close()
    before_fatal = _db_fingerprint(fatal_db)
    fatal_proc = run_worker(fatal_db, fatal_out, AS_OF)
    assert fatal_proc.returncode != 0
    assert fatal_proc.stderr.strip()
    assert not fatal_out.exists()
    assert not Path(str(fatal_out) + ".tmp").exists()
    assert _db_fingerprint(fatal_db) == before_fatal
