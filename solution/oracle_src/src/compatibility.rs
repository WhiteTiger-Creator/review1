use std::collections::{HashMap, HashSet};

use crate::checksum::{normalize_content_type, normalize_method};
use crate::model::{
    ApiOperation, Deployment, Runbook, Step, API_RETRY, DB_READ_RETRY, DB_WRITE_RETRY, LOCAL_RETRY,
};

pub fn applied_status(dep: &Deployment, rb: &Runbook) -> (String, bool, bool) {
    match dep.applied_runbooks.get(&rb.runbook_id) {
        None => ("not_applied".to_string(), false, true),
        Some(stored) if stored == &rb.checksum_sha256 => ("matched".to_string(), true, false),
        Some(_) => ("drift".to_string(), false, false),
    }
}

pub fn has_checksum_drift(dep: &Deployment, rb: &Runbook) -> bool {
    match dep.applied_runbooks.get(&rb.runbook_id) {
        Some(stored) => stored != &rb.checksum_sha256,
        None => false,
    }
}

pub fn validate_retry_policy_only(step: &Step, op: Option<&ApiOperation>) -> Option<&'static str> {
    match step.step_kind.as_str() {
        "local_prepare" | "local_finalize" => {
            if !LOCAL_RETRY.contains(&step.retry_mode.as_str()) {
                return Some("invalid_retry_policy");
            }
        }
        "database_read" => {
            if !DB_READ_RETRY.contains(&step.retry_mode.as_str()) {
                return Some("invalid_retry_policy");
            }
        }
        "database_write" => {
            if !DB_WRITE_RETRY.contains(&step.retry_mode.as_str()) {
                return Some("invalid_retry_policy");
            }
        }
        "api_request" => {
            if !API_RETRY.contains(&step.retry_mode.as_str()) {
                return Some("invalid_retry_policy");
            }
            if step.retry_mode == "safe" {
                if let Some(op) = op {
                    if !op.idempotent {
                        return Some("invalid_retry_policy");
                    }
                }
            }
        }
        _ => return Some("invalid_retry_policy"),
    }
    if step.retry_mode == "idempotency_key_required" && step.step_kind != "api_request" {
        return Some("invalid_retry_policy");
    }
    None
}

pub fn validate_missing_idempotency_key(step: &Step) -> Option<&'static str> {
    if step.step_kind == "api_request"
        && step.retry_mode == "idempotency_key_required"
        && step.idempotency_key_source_or_null.is_none()
    {
        Some("missing_idempotency_key_source")
    } else {
        None
    }
}

pub fn validate_retry(step: &Step, op: Option<&ApiOperation>) -> Option<&'static str> {
    validate_retry_policy_only(step, op).or_else(|| validate_missing_idempotency_key(step))
}

pub fn validate_api_step(step: &Step, op: &ApiOperation) -> Option<&'static str> {
    let norm_method = normalize_method(step.http_method_or_null.as_deref().unwrap_or(""));
    if norm_method.as_deref() != Some(op.method.as_str()) {
        return Some("api_method_mismatch");
    }
    let norm_ct =
        normalize_content_type(step.request_content_type_or_null.as_deref().unwrap_or(""));
    if let Some(ct) = norm_ct {
        if !op.accepted_request_content_types.contains(&ct) {
            return Some("api_content_type_mismatch");
        }
    } else {
        return Some("api_content_type_mismatch");
    }
    let accepted: HashSet<i64> = step.accepted_statuses.iter().copied().collect();
    let success: HashSet<i64> = op.success_statuses.iter().copied().collect();
    if !accepted.is_subset(&success) {
        return Some("api_success_status_mismatch");
    }
    None
}

pub fn initial_capabilities(
    dep: &Deployment,
    runbooks: &HashMap<String, Runbook>,
) -> HashSet<String> {
    let mut caps = dep.capabilities.clone();
    for (rb_id, stored) in &dep.applied_runbooks {
        if let Some(rb) = runbooks.get(rb_id) {
            if stored == &rb.checksum_sha256 {
                for step in &rb.steps {
                    caps.extend(step.provided_capabilities.iter().cloned());
                }
            }
        }
    }
    caps
}

/// Project remaining required capabilities for report rows.
///
/// Capability identities are exact UTF-8 strings (no case folding or
/// trimming). Deduplicate, subtract every capability already present in
/// the initial applied deployment state, then sort by ascending UTF-8
/// byte order. Capabilities produced later in the same plan are NOT
/// removed here — only the initial applied set is subtracted.
pub fn project_required_capabilities(
    declared: &[String],
    initial: &HashSet<String>,
) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut remaining = Vec::new();
    for cap in declared {
        if !seen.insert(cap.clone()) {
            continue;
        }
        if initial.contains(cap) {
            continue;
        }
        remaining.push(cap.clone());
    }
    remaining.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    remaining
}
