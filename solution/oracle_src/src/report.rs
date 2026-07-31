use std::collections::HashMap;

use anyhow::Result;

use crate::cli::ts_cmp;
use crate::models::*;

pub fn build_report(
    results: &[AssertionResultRow],
    credentials: &HashMap<String, CredentialRow>,
    challenges: &HashMap<String, ChallengeRow>,
    as_of: &str,
    pending_count: i64,
) -> Report {
    let mut assertion_rows: Vec<AssertionReportRow> = results
        .iter()
        .map(|r| AssertionReportRow {
            assertion_id: r.assertion_id.clone(),
            credential_id: r.credential_id.clone(),
            challenge_id: r.challenge_id.clone(),
            received_at: r.received_at.clone(),
            status: r.status.clone(),
            reason_or_null: r.reason_or_null.clone(),
            risk_or_null: r.risk_or_null.clone(),
            user_present_or_null: r.user_present_or_null,
            user_verified_or_null: r.user_verified_or_null,
            backup_eligible_or_null: r.backup_eligible_or_null,
            backup_state_or_null: r.backup_state_or_null,
            sign_count_or_null: r.sign_count_or_null,
            sign_count_before_or_null: r.sign_count_before_or_null,
            sign_count_after_or_null: r.sign_count_after_or_null,
            challenge_consumed: r.challenge_consumed,
            credential_mutated: r.credential_mutated,
        })
        .collect();
    assertion_rows.sort_by(|a, b| {
        a.received_at
            .cmp(&b.received_at)
            .then(a.assertion_id.cmp(&b.assertion_id))
    });

    let mut credential_rows: Vec<CredentialReportRow> = credentials
        .values()
        .map(|c| CredentialReportRow {
            credential_id: c.credential_id.clone(),
            user_id: c.user_id.clone(),
            rp_id: c.rp_id.clone(),
            status: c.status.clone(),
            sign_count: c.sign_count as i64,
            backup_eligible: if c.backup_eligible { 1 } else { 0 },
            backup_state: if c.backup_state { 1 } else { 0 },
            last_used_at_or_null: c.last_used_at.clone(),
        })
        .collect();
    credential_rows.sort_by(|a, b| {
        a.rp_id
            .cmp(&b.rp_id)
            .then(a.user_id.cmp(&b.user_id))
            .then(a.credential_id.cmp(&b.credential_id))
    });

    let mut challenge_rows: Vec<ChallengeReportRow> = challenges
        .values()
        .map(|c| {
            let status = if c.consumed_at.is_some() {
                "consumed".to_string()
            } else if ts_cmp(&c.expires_at, as_of) == std::cmp::Ordering::Less {
                "expired".to_string()
            } else {
                "available".to_string()
            };
            ChallengeReportRow {
                challenge_id: c.challenge_id.clone(),
                rp_id: c.rp_id.clone(),
                status,
                issued_at: c.issued_at.clone(),
                expires_at: c.expires_at.clone(),
                consumed_at_or_null: c.consumed_at.clone(),
                consumed_by_assertion_id_or_null: c.consumed_by_assertion_id.clone(),
            }
        })
        .collect();
    challenge_rows.sort_by(|a, b| {
        a.rp_id
            .cmp(&b.rp_id)
            .then(a.challenge_id.cmp(&b.challenge_id))
    });

    let processed = assertion_rows.len() as i64;
    let accepted = assertion_rows
        .iter()
        .filter(|r| r.status == "accepted")
        .count() as i64;
    let rejected = assertion_rows
        .iter()
        .filter(|r| r.status == "rejected")
        .count() as i64;
    let risk = assertion_rows
        .iter()
        .filter(|r| r.risk_or_null.is_some())
        .count() as i64;
    let consumed = challenge_rows
        .iter()
        .filter(|r| r.status == "consumed")
        .count() as i64;
    let active = credential_rows
        .iter()
        .filter(|r| r.status == "active")
        .count() as i64;
    let quarantined = credential_rows
        .iter()
        .filter(|r| r.status == "quarantined")
        .count() as i64;
    let revoked = credential_rows
        .iter()
        .filter(|r| r.status == "revoked")
        .count() as i64;

    Report {
        assertion_rows,
        credential_rows,
        challenge_rows,
        summary: Summary {
            processed_assertion_count: processed,
            accepted_assertion_count: accepted,
            rejected_assertion_count: rejected,
            risk_assertion_count: risk,
            consumed_challenge_count: consumed,
            active_credential_count: active,
            quarantined_credential_count: quarantined,
            revoked_credential_count: revoked,
            pending_future_job_count: pending_count,
        },
    }
}

pub fn serialize_report(report: &Report) -> Result<Vec<u8>> {
    let mut buf = Vec::new();
    let formatter = serde_json::ser::PrettyFormatter::with_indent(b"  ");
    let mut ser = serde_json::Serializer::with_formatter(&mut buf, formatter);
    serde::Serialize::serialize(report, &mut ser)?;
    buf.push(b'\n');
    // Ensure no trailing spaces on lines.
    let text = String::from_utf8(buf)?;
    let cleaned: String = text
        .lines()
        .map(|line| line.trim_end())
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    Ok(cleaned.into_bytes())
}
