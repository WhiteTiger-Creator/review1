use std::collections::HashMap;
use std::path::Path;

use anyhow::{bail, Result};

use crate::authenticator_data::parse_authenticator_data;
use crate::cli::{parse_as_of, ts_cmp, CliArgs};
use crate::client_data::{parse_client_data, validate_client_data_type};
use crate::crypto::{b64url_encode, sha256, signed_message, verify_es256_der};
use crate::database::{
    insert_result, load_all_results, load_challenges, load_credentials, load_eligible_jobs,
    load_origins, load_policies, load_users, mark_job_processed, preflight,
    update_challenge_consumed, update_credential, AuditDb,
};
use crate::models::*;
use crate::output::{cleanup_outputs, write_report_atomic};
use crate::policy::{credential_is_inactive, evaluate_counter, CounterDecision};
use crate::report::build_report;

pub fn run_worker(args: &CliArgs) -> Result<()> {
    let as_of = parse_as_of(&args.as_of)?;
    let output_parent = args
        .output
        .parent()
        .ok_or_else(|| anyhow::anyhow!("output parent missing"))?;
    if !output_parent.exists() {
        bail!("output parent directory does not exist");
    }

    // Remove stale output before validation begins.
    cleanup_outputs(&args.output)?;

    let mut db = AuditDb::open(&args.database)?;
    preflight(&db.conn)?;

    let tx = db.begin_write()?;
    let policies = load_policies(&tx)?;
    let origins = load_origins(&tx)?;
    let users = load_users(&tx)?;
    let mut credentials = load_credentials(&tx)?;
    let mut challenges = load_challenges(&tx)?;
    let jobs = load_eligible_jobs(&tx, &as_of)?;

    for job in jobs {
        let (result, cred_update, chal_consume) =
            process_job(&job, &policies, &origins, &users, &credentials, &challenges)?;
        insert_result(&tx, &result)?;
        mark_job_processed(&tx, &job.assertion_id)?;
        if let Some(cid) = chal_consume {
            if let Some(ch) = challenges.get_mut(&cid) {
                ch.consumed_at = Some(job.received_at.clone());
                ch.consumed_by_assertion_id = Some(job.assertion_id.clone());
            }
            update_challenge_consumed(&tx, &cid, &job.received_at, &job.assertion_id)?;
        }
        if let Some(cred) = cred_update {
            credentials.insert(cred.credential_id.clone(), cred.clone());
            update_credential(&tx, &cred)?;
        }
    }

    let results = load_all_results(&tx)?;
    // Refresh credential/challenge maps after mutations for report.
    let credentials = load_credentials(&tx)?;
    let challenges = load_challenges(&tx)?;
    let pending = crate::database::count_pending_jobs(&tx)?;
    let report = build_report(&results, &credentials, &challenges, &as_of, pending);

    // Keep transaction open until report serialization succeeds conceptually;
    // commit state then write report. If report write fails, roll back by
    // aborting before commit — so serialize first into memory, commit, then write.
    let report_bytes = crate::report::serialize_report(&report)?;
    tx.commit()?;

    if let Err(e) = write_report_atomic(&args.output, &report_bytes) {
        cleanup_outputs(&args.output)?;
        return Err(e);
    }
    Ok(())
}

fn process_job(
    job: &AssertionJob,
    policies: &HashMap<String, RpPolicy>,
    origins: &HashMap<String, std::collections::HashSet<String>>,
    users: &HashMap<String, UserRow>,
    credentials: &HashMap<String, CredentialRow>,
    challenges: &HashMap<String, ChallengeRow>,
) -> Result<(AssertionResultRow, Option<CredentialRow>, Option<String>)> {
    let mut flags: Option<ParsedAuthData> = None;

    let cred = match credentials.get(&job.credential_id) {
        None => {
            return Ok((
                reject(job, "credential_unknown", None, flags, None, None, 0, 0),
                None,
                None,
            ));
        }
        Some(c) => c.clone(),
    };
    let sign_before = Some(cred.sign_count as i64);
    let mut sign_after = Some(cred.sign_count as i64);

    let user = users.get(&cred.user_id);
    let user_status = user.map(|u| u.status.as_str()).unwrap_or("disabled");
    if credential_is_inactive(&cred, user_status) {
        return Ok((
            reject(
                job,
                "credential_inactive",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    let challenge = match challenges.get(&job.challenge_id) {
        None => {
            return Ok((
                reject(
                    job,
                    "challenge_unknown",
                    None,
                    flags,
                    sign_before,
                    sign_after,
                    0,
                    0,
                ),
                None,
                None,
            ));
        }
        Some(c) => c.clone(),
    };

    let client = match parse_client_data(&job.client_data_json) {
        Ok(c) => c,
        Err(reason) => {
            return Ok((
                reject(job, reason, None, flags, sign_before, sign_after, 0, 0),
                None,
                None,
            ));
        }
    };
    if let Err(reason) = validate_client_data_type(&client) {
        return Ok((
            reject(job, reason, None, flags, sign_before, sign_after, 0, 0),
            None,
            None,
        ));
    }

    let auth = match parse_authenticator_data(&job.authenticator_data) {
        Ok(a) => a,
        Err(reason) => {
            return Ok((
                reject(job, reason, None, flags, sign_before, sign_after, 0, 0),
                None,
                None,
            ));
        }
    };
    flags = Some(auth.clone());

    let message = signed_message(&job.authenticator_data, &job.client_data_json);
    if verify_es256_der(&cred.public_key_sec1, &message, &job.signature_der).is_err() {
        return Ok((
            reject(
                job,
                "invalid_signature",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    if ts_cmp(&job.received_at, &challenge.issued_at) == std::cmp::Ordering::Less {
        return Ok((
            reject(
                job,
                "challenge_not_yet_valid",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }
    if ts_cmp(&job.received_at, &challenge.expires_at) != std::cmp::Ordering::Less {
        return Ok((
            reject(
                job,
                "challenge_expired",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }
    if challenge.consumed_at.is_some() || challenge.consumed_by_assertion_id.is_some() {
        return Ok((
            reject(
                job,
                "challenge_already_consumed",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    let expected_chal = b64url_encode(&challenge.challenge_bytes);
    if client.challenge != expected_chal || challenge.rp_id != cred.rp_id {
        return Ok((
            reject(
                job,
                "challenge_mismatch",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    let allowed = origins.get(&cred.rp_id).cloned().unwrap_or_default();
    if !allowed.contains(&client.origin) {
        return Ok((
            reject(
                job,
                "origin_mismatch",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }
    if client.cross_origin == Some(true) {
        return Ok((
            reject(
                job,
                "cross_origin_disallowed",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    let expected_rp_hash = sha256(cred.rp_id.as_bytes());
    if auth.rp_id_hash != expected_rp_hash {
        return Ok((
            reject(
                job,
                "rp_id_hash_mismatch",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    let policy = policies
        .get(&cred.rp_id)
        .ok_or_else(|| anyhow::anyhow!("missing rp policy"))?;

    if !auth.user_present {
        return Ok((
            reject(
                job,
                "user_presence_required",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }
    if policy.require_user_verification && !auth.user_verified {
        return Ok((
            reject(
                job,
                "user_verification_required",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }
    if auth.backup_state && !auth.backup_eligible {
        return Ok((
            reject(
                job,
                "backup_flags_invalid",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }
    if auth.backup_eligible != cred.backup_eligible {
        return Ok((
            reject(
                job,
                "backup_eligibility_changed",
                None,
                flags,
                sign_before,
                sign_after,
                0,
                0,
            ),
            None,
            None,
        ));
    }

    match evaluate_counter(
        cred.sign_count,
        auth.sign_count,
        cred.backup_eligible,
        &policy.backup_counter_policy,
    ) {
        CounterDecision::RejectReplay => {
            let mut updated = cred.clone();
            updated.status = "quarantined".to_string();
            sign_after = Some(cred.sign_count as i64);
            Ok((
                reject(
                    job,
                    "signature_counter_replay",
                    None,
                    flags,
                    sign_before,
                    sign_after,
                    1,
                    1,
                ),
                Some(updated),
                Some(challenge.challenge_id.clone()),
            ))
        }
        CounterDecision::Accept {
            new_sign_count,
            risk,
        } => {
            let mut updated = cred.clone();
            updated.sign_count = new_sign_count;
            updated.backup_state = auth.backup_state;
            updated.last_used_at = Some(job.received_at.clone());
            sign_after = Some(new_sign_count as i64);
            let mutated = (updated.sign_count != cred.sign_count)
                || (updated.backup_state != cred.backup_state)
                || (updated.last_used_at != cred.last_used_at)
                || (updated.status != cred.status);
            Ok((
                accept(
                    job,
                    risk.map(|s| s.to_string()),
                    flags,
                    sign_before,
                    sign_after,
                    1,
                    if mutated { 1 } else { 0 },
                ),
                Some(updated),
                Some(challenge.challenge_id.clone()),
            ))
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn reject(
    job: &AssertionJob,
    reason: &str,
    risk: Option<String>,
    flags: Option<ParsedAuthData>,
    sign_before: Option<i64>,
    sign_after: Option<i64>,
    challenge_consumed: i64,
    credential_mutated: i64,
) -> AssertionResultRow {
    AssertionResultRow {
        assertion_id: job.assertion_id.clone(),
        status: "rejected".to_string(),
        reason_or_null: Some(reason.to_string()),
        risk_or_null: risk,
        credential_id: job.credential_id.clone(),
        challenge_id: job.challenge_id.clone(),
        received_at: job.received_at.clone(),
        user_present_or_null: flags.as_ref().map(|f| if f.user_present { 1 } else { 0 }),
        user_verified_or_null: flags.as_ref().map(|f| if f.user_verified { 1 } else { 0 }),
        backup_eligible_or_null: flags
            .as_ref()
            .map(|f| if f.backup_eligible { 1 } else { 0 }),
        backup_state_or_null: flags.as_ref().map(|f| if f.backup_state { 1 } else { 0 }),
        sign_count_or_null: flags.as_ref().map(|f| f.sign_count as i64),
        sign_count_before_or_null: sign_before,
        sign_count_after_or_null: sign_after,
        challenge_consumed,
        credential_mutated,
    }
}

#[allow(clippy::too_many_arguments)]
fn accept(
    job: &AssertionJob,
    risk: Option<String>,
    flags: Option<ParsedAuthData>,
    sign_before: Option<i64>,
    sign_after: Option<i64>,
    challenge_consumed: i64,
    credential_mutated: i64,
) -> AssertionResultRow {
    AssertionResultRow {
        assertion_id: job.assertion_id.clone(),
        status: "accepted".to_string(),
        reason_or_null: None,
        risk_or_null: risk,
        credential_id: job.credential_id.clone(),
        challenge_id: job.challenge_id.clone(),
        received_at: job.received_at.clone(),
        user_present_or_null: flags.as_ref().map(|f| if f.user_present { 1 } else { 0 }),
        user_verified_or_null: flags.as_ref().map(|f| if f.user_verified { 1 } else { 0 }),
        backup_eligible_or_null: flags
            .as_ref()
            .map(|f| if f.backup_eligible { 1 } else { 0 }),
        backup_state_or_null: flags.as_ref().map(|f| if f.backup_state { 1 } else { 0 }),
        sign_count_or_null: flags.as_ref().map(|f| f.sign_count as i64),
        sign_count_before_or_null: sign_before,
        sign_count_after_or_null: sign_after,
        challenge_consumed,
        credential_mutated,
    }
}

pub fn fatal_cleanup(output: &Path) {
    let _ = cleanup_outputs(output);
}
