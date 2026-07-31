use std::collections::{HashMap, HashSet};
use std::path::Path;

use anyhow::{bail, Context, Result};
use rusqlite::{Connection, OptionalExtension, Transaction, TransactionBehavior};

use crate::cli::{parse_as_of, ts_cmp};
use crate::models::*;

pub struct AuditDb {
    pub conn: Connection,
}

impl AuditDb {
    pub fn open(path: &Path) -> Result<Self> {
        let conn = Connection::open(path).context("failed to open database")?;
        conn.pragma_update(None, "foreign_keys", "ON")?;
        Ok(Self { conn })
    }

    pub fn begin_write(&mut self) -> Result<Transaction<'_>> {
        Ok(self
            .conn
            .transaction_with_behavior(TransactionBehavior::Deferred)?)
    }
}

pub fn preflight(conn: &Connection) -> Result<()> {
    require_tables(conn)?;
    let version: i64 = conn.query_row("SELECT schema_version FROM schema_metadata", [], |r| {
        r.get(0)
    })?;
    if version != 1 {
        bail!("schema_version must be 1");
    }
    let meta_count: i64 =
        conn.query_row("SELECT COUNT(*) FROM schema_metadata", [], |r| r.get(0))?;
    if meta_count != 1 {
        bail!("schema_metadata must have exactly one row");
    }

    validate_rp_policies(conn)?;
    validate_rp_origins(conn)?;
    validate_users(conn)?;
    validate_credentials(conn)?;
    validate_challenges(conn)?;
    validate_jobs_and_results(conn)?;
    Ok(())
}

fn require_tables(conn: &Connection) -> Result<()> {
    let required = [
        ("schema_metadata", &["schema_version"][..]),
        (
            "rp_policies",
            &[
                "rp_id",
                "require_user_verification",
                "backup_counter_policy",
            ][..],
        ),
        ("rp_origins", &["rp_id", "origin"][..]),
        ("users", &["user_id", "status"][..]),
        (
            "credentials",
            &[
                "credential_id",
                "user_id",
                "rp_id",
                "public_key_sec1",
                "sign_count",
                "backup_eligible",
                "backup_state",
                "status",
                "last_used_at",
            ][..],
        ),
        (
            "challenges",
            &[
                "challenge_id",
                "rp_id",
                "challenge_bytes",
                "issued_at",
                "expires_at",
                "consumed_at",
                "consumed_by_assertion_id",
            ][..],
        ),
        (
            "assertion_jobs",
            &[
                "assertion_id",
                "received_at",
                "event_seq",
                "credential_id",
                "challenge_id",
                "client_data_json",
                "authenticator_data",
                "signature_der",
                "status",
            ][..],
        ),
        (
            "assertion_results",
            &[
                "assertion_id",
                "status",
                "reason_or_null",
                "risk_or_null",
                "credential_id",
                "challenge_id",
                "received_at",
                "user_present_or_null",
                "user_verified_or_null",
                "backup_eligible_or_null",
                "backup_state_or_null",
                "sign_count_or_null",
                "sign_count_before_or_null",
                "sign_count_after_or_null",
                "challenge_consumed",
                "credential_mutated",
            ][..],
        ),
    ];
    for (table, cols) in required {
        let exists: bool = conn.query_row(
            "SELECT COUNT(*) > 0 FROM sqlite_master WHERE type='table' AND name=?1",
            [table],
            |r| r.get(0),
        )?;
        if !exists {
            bail!("missing required table: {table}");
        }
        let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
        let found: HashSet<String> = stmt
            .query_map([], |r| r.get::<_, String>(1))?
            .collect::<Result<HashSet<_>, _>>()?;
        for c in cols {
            if !found.contains(*c) {
                bail!("missing required column {table}.{c}");
            }
        }
    }
    Ok(())
}

fn validate_timestamp(raw: &str, field: &str) -> Result<()> {
    parse_as_of(raw).with_context(|| format!("invalid timestamp in {field}"))?;
    Ok(())
}

fn validate_bool01(v: i64, field: &str) -> Result<bool> {
    match v {
        0 => Ok(false),
        1 => Ok(true),
        _ => bail!("invalid boolean integer in {field}"),
    }
}

fn validate_rp_policies(conn: &Connection) -> Result<()> {
    let mut stmt = conn.prepare(
        "SELECT rp_id, require_user_verification, backup_counter_policy FROM rp_policies",
    )?;
    let rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, String>(0)?,
            r.get::<_, i64>(1)?,
            r.get::<_, String>(2)?,
        ))
    })?;
    for row in rows {
        let (rp_id, uv, policy) = row?;
        validate_bool01(
            uv,
            &format!("rp_policies.require_user_verification:{rp_id}"),
        )?;
        if policy != "strict" && policy != "backup_aware" {
            bail!("invalid backup_counter_policy for {rp_id}");
        }
    }
    Ok(())
}

fn validate_rp_origins(conn: &Connection) -> Result<()> {
    let mut stmt = conn.prepare("SELECT rp_id, origin FROM rp_origins")?;
    let rows = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?;
    for row in rows {
        let (rp_id, _origin) = row?;
        let exists: bool = conn.query_row(
            "SELECT COUNT(*) > 0 FROM rp_policies WHERE rp_id=?1",
            [&rp_id],
            |r| r.get(0),
        )?;
        if !exists {
            bail!("broken foreign key rp_origins.rp_id={rp_id}");
        }
    }
    Ok(())
}

fn validate_users(conn: &Connection) -> Result<()> {
    let mut stmt = conn.prepare("SELECT user_id, status FROM users")?;
    let rows = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?;
    for row in rows {
        let (uid, status) = row?;
        if status != "active" && status != "disabled" {
            bail!("invalid user status for {uid}");
        }
    }
    Ok(())
}

fn validate_credentials(conn: &Connection) -> Result<()> {
    let mut stmt = conn.prepare(
        "SELECT credential_id, user_id, rp_id, public_key_sec1, sign_count, backup_eligible, backup_state, status, last_used_at FROM credentials",
    )?;
    let rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, String>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, Vec<u8>>(3)?,
            r.get::<_, i64>(4)?,
            r.get::<_, i64>(5)?,
            r.get::<_, i64>(6)?,
            r.get::<_, String>(7)?,
            r.get::<_, Option<String>>(8)?,
        ))
    })?;
    for row in rows {
        let (cid, uid, rp, pk, sc, be, bs, status, last) = row?;
        let user_ok: bool = conn.query_row(
            "SELECT COUNT(*) > 0 FROM users WHERE user_id=?1",
            [&uid],
            |r| r.get(0),
        )?;
        if !user_ok {
            bail!("broken foreign key credentials.user_id");
        }
        let rp_ok: bool = conn.query_row(
            "SELECT COUNT(*) > 0 FROM rp_policies WHERE rp_id=?1",
            [&rp],
            |r| r.get(0),
        )?;
        if !rp_ok {
            bail!("broken foreign key credentials.rp_id");
        }
        if pk.len() != 65 || pk[0] != 0x04 {
            bail!("invalid public_key_sec1 for {cid}");
        }
        if !(0..=4_294_967_295).contains(&sc) {
            bail!("sign_count out of range for {cid}");
        }
        let be_b = validate_bool01(be, "backup_eligible")?;
        let bs_b = validate_bool01(bs, "backup_state")?;
        if bs_b && !be_b {
            bail!("BS set while BE clear for {cid}");
        }
        if status != "active" && status != "quarantined" && status != "revoked" {
            bail!("invalid credential status for {cid}");
        }
        if let Some(ts) = last {
            validate_timestamp(&ts, "credentials.last_used_at")?;
        }
    }
    Ok(())
}

fn validate_challenges(conn: &Connection) -> Result<()> {
    let mut stmt = conn.prepare(
        "SELECT challenge_id, rp_id, challenge_bytes, issued_at, expires_at, consumed_at, consumed_by_assertion_id FROM challenges",
    )?;
    let rows = stmt.query_map([], |r| {
        Ok((
            r.get::<_, String>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, Vec<u8>>(2)?,
            r.get::<_, String>(3)?,
            r.get::<_, String>(4)?,
            r.get::<_, Option<String>>(5)?,
            r.get::<_, Option<String>>(6)?,
        ))
    })?;
    for row in rows {
        let (cid, rp, bytes, issued, expires, consumed_at, consumed_by) = row?;
        let rp_ok: bool = conn.query_row(
            "SELECT COUNT(*) > 0 FROM rp_policies WHERE rp_id=?1",
            [&rp],
            |r| r.get(0),
        )?;
        if !rp_ok {
            bail!("broken foreign key challenges.rp_id");
        }
        if bytes.len() < 16 || bytes.len() > 64 {
            bail!("invalid challenge_bytes length for {cid}");
        }
        validate_timestamp(&issued, "challenges.issued_at")?;
        validate_timestamp(&expires, "challenges.expires_at")?;
        if ts_cmp(&issued, &expires) == std::cmp::Ordering::Greater {
            bail!("issued_at later than expires_at for {cid}");
        }
        match (&consumed_at, &consumed_by) {
            (None, None) => {}
            (Some(a), Some(_)) => validate_timestamp(a, "challenges.consumed_at")?,
            _ => bail!("challenge consumed fields disagree for {cid}"),
        }
    }
    Ok(())
}

fn validate_jobs_and_results(conn: &Connection) -> Result<()> {
    let mut stmt =
        conn.prepare("SELECT assertion_id, received_at, event_seq, status FROM assertion_jobs")?;
    let jobs: Vec<(String, String, i64, String)> = stmt
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)))?
        .collect::<Result<Vec<_>, _>>()?;
    for (aid, received, event_seq, status) in &jobs {
        validate_timestamp(received, "assertion_jobs.received_at")?;
        if *event_seq < 0 {
            bail!("negative event_seq for {aid}");
        }
        if status != "pending" && status != "processed" {
            bail!("invalid job status for {aid}");
        }
        let has_result: bool = conn.query_row(
            "SELECT COUNT(*) > 0 FROM assertion_results WHERE assertion_id=?1",
            [aid],
            |r| r.get(0),
        )?;
        if status == "pending" && has_result {
            bail!("assertion result exists for pending job {aid}");
        }
        if status == "processed" && !has_result {
            bail!("processed job has no assertion result {aid}");
        }
    }
    Ok(())
}

pub fn load_policies(conn: &Connection) -> Result<HashMap<String, RpPolicy>> {
    let mut stmt = conn.prepare(
        "SELECT rp_id, require_user_verification, backup_counter_policy FROM rp_policies",
    )?;
    let mut map = HashMap::new();
    let rows = stmt.query_map([], |r| {
        Ok(RpPolicy {
            rp_id: r.get(0)?,
            require_user_verification: r.get::<_, i64>(1)? == 1,
            backup_counter_policy: r.get(2)?,
        })
    })?;
    for row in rows {
        let p = row?;
        map.insert(p.rp_id.clone(), p);
    }
    Ok(map)
}

pub fn load_origins(conn: &Connection) -> Result<HashMap<String, HashSet<String>>> {
    let mut stmt = conn.prepare("SELECT rp_id, origin FROM rp_origins")?;
    let mut map: HashMap<String, HashSet<String>> = HashMap::new();
    let rows = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?;
    for row in rows {
        let (rp, origin) = row?;
        map.entry(rp).or_default().insert(origin);
    }
    Ok(map)
}

pub fn load_users(conn: &Connection) -> Result<HashMap<String, UserRow>> {
    let mut stmt = conn.prepare("SELECT user_id, status FROM users")?;
    let mut map = HashMap::new();
    let rows = stmt.query_map([], |r| {
        Ok(UserRow {
            user_id: r.get(0)?,
            status: r.get(1)?,
        })
    })?;
    for row in rows {
        let u = row?;
        map.insert(u.user_id.clone(), u);
    }
    Ok(map)
}

pub fn load_credentials(conn: &Connection) -> Result<HashMap<String, CredentialRow>> {
    let mut stmt = conn.prepare(
        "SELECT credential_id, user_id, rp_id, public_key_sec1, sign_count, backup_eligible, backup_state, status, last_used_at FROM credentials",
    )?;
    let mut map = HashMap::new();
    let rows = stmt.query_map([], |r| {
        Ok(CredentialRow {
            credential_id: r.get(0)?,
            user_id: r.get(1)?,
            rp_id: r.get(2)?,
            public_key_sec1: r.get(3)?,
            sign_count: r.get::<_, i64>(4)? as u32,
            backup_eligible: r.get::<_, i64>(5)? == 1,
            backup_state: r.get::<_, i64>(6)? == 1,
            status: r.get(7)?,
            last_used_at: r.get(8)?,
        })
    })?;
    for row in rows {
        let c = row?;
        map.insert(c.credential_id.clone(), c);
    }
    Ok(map)
}

pub fn load_challenges(conn: &Connection) -> Result<HashMap<String, ChallengeRow>> {
    let mut stmt = conn.prepare(
        "SELECT challenge_id, rp_id, challenge_bytes, issued_at, expires_at, consumed_at, consumed_by_assertion_id FROM challenges",
    )?;
    let mut map = HashMap::new();
    let rows = stmt.query_map([], |r| {
        Ok(ChallengeRow {
            challenge_id: r.get(0)?,
            rp_id: r.get(1)?,
            challenge_bytes: r.get(2)?,
            issued_at: r.get(3)?,
            expires_at: r.get(4)?,
            consumed_at: r.get(5)?,
            consumed_by_assertion_id: r.get(6)?,
        })
    })?;
    for row in rows {
        let c = row?;
        map.insert(c.challenge_id.clone(), c);
    }
    Ok(map)
}

pub fn load_eligible_jobs(conn: &Connection, as_of: &str) -> Result<Vec<AssertionJob>> {
    let mut stmt = conn.prepare(
        "SELECT assertion_id, received_at, event_seq, credential_id, challenge_id, client_data_json, authenticator_data, signature_der, status
         FROM assertion_jobs WHERE status='pending' AND received_at <= ?1",
    )?;
    let mut jobs: Vec<AssertionJob> = stmt
        .query_map([as_of], |r| {
            Ok(AssertionJob {
                assertion_id: r.get(0)?,
                received_at: r.get(1)?,
                event_seq: r.get(2)?,
                credential_id: r.get(3)?,
                challenge_id: r.get(4)?,
                client_data_json: r.get(5)?,
                authenticator_data: r.get(6)?,
                signature_der: r.get(7)?,
                status: r.get(8)?,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;
    jobs.sort_by(|a, b| a.assertion_id.cmp(&b.assertion_id));
    Ok(jobs)
}

pub fn count_pending_jobs(conn: &Connection) -> Result<i64> {
    Ok(conn.query_row(
        "SELECT COUNT(*) FROM assertion_jobs WHERE status='pending'",
        [],
        |r| r.get(0),
    )?)
}

pub fn insert_result(tx: &Transaction<'_>, row: &AssertionResultRow) -> Result<()> {
    tx.execute(
        "INSERT INTO assertion_results (
            assertion_id, status, reason_or_null, risk_or_null, credential_id, challenge_id, received_at,
            user_present_or_null, user_verified_or_null, backup_eligible_or_null, backup_state_or_null,
            sign_count_or_null, sign_count_before_or_null, sign_count_after_or_null,
            challenge_consumed, credential_mutated
        ) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16)",
        rusqlite::params![
            row.assertion_id,
            row.status,
            row.reason_or_null,
            row.risk_or_null,
            row.credential_id,
            row.challenge_id,
            row.received_at,
            row.user_present_or_null,
            row.user_verified_or_null,
            row.backup_eligible_or_null,
            row.backup_state_or_null,
            row.sign_count_or_null,
            row.sign_count_before_or_null,
            row.sign_count_after_or_null,
            row.challenge_consumed,
            row.credential_mutated,
        ],
    )?;
    Ok(())
}

pub fn mark_job_processed(tx: &Transaction<'_>, assertion_id: &str) -> Result<()> {
    tx.execute(
        "UPDATE assertion_jobs SET status='processed' WHERE assertion_id=?1",
        [assertion_id],
    )?;
    Ok(())
}

pub fn update_challenge_consumed(
    tx: &Transaction<'_>,
    challenge_id: &str,
    consumed_at: &str,
    assertion_id: &str,
) -> Result<()> {
    tx.execute(
        "UPDATE challenges SET consumed_at=?1, consumed_by_assertion_id=?2 WHERE challenge_id=?3",
        rusqlite::params![consumed_at, assertion_id, challenge_id],
    )?;
    Ok(())
}

pub fn update_credential(tx: &Transaction<'_>, cred: &CredentialRow) -> Result<()> {
    tx.execute(
        "UPDATE credentials SET sign_count=?1, backup_state=?2, status=?3, last_used_at=?4 WHERE credential_id=?5",
        rusqlite::params![
            cred.sign_count as i64,
            if cred.backup_state { 1 } else { 0 },
            cred.status,
            cred.last_used_at,
            cred.credential_id,
        ],
    )?;
    Ok(())
}

pub fn load_all_results(conn: &Connection) -> Result<Vec<AssertionResultRow>> {
    let mut stmt = conn.prepare(
        "SELECT assertion_id, status, reason_or_null, risk_or_null, credential_id, challenge_id, received_at,
                user_present_or_null, user_verified_or_null, backup_eligible_or_null, backup_state_or_null,
                sign_count_or_null, sign_count_before_or_null, sign_count_after_or_null,
                challenge_consumed, credential_mutated
         FROM assertion_results",
    )?;
    let rows = stmt
        .query_map([], |r| {
            Ok(AssertionResultRow {
                assertion_id: r.get(0)?,
                status: r.get(1)?,
                reason_or_null: r.get(2)?,
                risk_or_null: r.get(3)?,
                credential_id: r.get(4)?,
                challenge_id: r.get(5)?,
                received_at: r.get(6)?,
                user_present_or_null: r.get(7)?,
                user_verified_or_null: r.get(8)?,
                backup_eligible_or_null: r.get(9)?,
                backup_state_or_null: r.get(10)?,
                sign_count_or_null: r.get(11)?,
                sign_count_before_or_null: r.get(12)?,
                sign_count_after_or_null: r.get(13)?,
                challenge_consumed: r.get(14)?,
                credential_mutated: r.get(15)?,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;
    Ok(rows)
}

pub fn get_job_status(conn: &Connection, assertion_id: &str) -> Result<Option<String>> {
    Ok(conn
        .query_row(
            "SELECT status FROM assertion_jobs WHERE assertion_id=?1",
            [assertion_id],
            |r| r.get(0),
        )
        .optional()?)
}
