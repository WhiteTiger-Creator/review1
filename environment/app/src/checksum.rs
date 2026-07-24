use std::collections::HashSet;

use serde_json::Value;

use crate::error::{FatalInputError, Result};
use crate::model::{Runbook, Step};

pub fn sort_utf8(values: &[String]) -> Vec<String> {
    let mut out = values.to_vec();
    out.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    out
}

pub fn validate_checksum_syntax(value: &str) -> bool {
    value.len() == 64
        && value
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

pub fn normalize_method(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.is_empty() || !trimmed.chars().all(|c| c.is_ascii_alphabetic()) {
        return None;
    }
    Some(trimmed.to_ascii_uppercase())
}

pub fn normalize_content_type(value: &str) -> Option<String> {
    let trimmed = value.trim().to_ascii_lowercase();
    if trimmed.is_empty() || trimmed.contains(';') {
        return None;
    }
    Some(trimmed)
}

fn json_string(s: &str) -> String {
    serde_json::to_string(s).expect("string json")
}

fn json_nullable_string(value: &Option<String>) -> String {
    match value {
        Some(s) => json_string(s),
        None => "null".to_string(),
    }
}

fn json_string_array(values: &[String]) -> String {
    let items: Vec<String> = values.iter().map(|v| json_string(v)).collect();
    format!("[{}]", items.join(","))
}

fn json_i64_array(values: &[i64]) -> String {
    let items: Vec<String> = values.iter().map(|v| v.to_string()).collect();
    format!("[{}]", items.join(","))
}

fn step_to_checksum_json(step: &Step) -> String {
    format!(
        "{{\"step_id\":{},\"step_rank\":{},\"step_kind\":{},\"requires_step_ids\":{},\"required_capabilities\":{},\"provided_capabilities\":{},\"api_operation_id_or_null\":{},\"http_method_or_null\":{},\"request_content_type_or_null\":{},\"accepted_statuses\":{},\"database_action_or_null\":{},\"retry_mode\":{},\"idempotency_key_source_or_null\":{}}}",
        json_string(&step.step_id),
        step.step_rank,
        json_string(&step.step_kind),
        json_string_array(&sort_utf8(&step.requires_step_ids)),
        json_string_array(&sort_utf8(&step.required_capabilities)),
        json_string_array(&sort_utf8(&step.provided_capabilities)),
        json_nullable_string(&step.api_operation_id_or_null),
        json_nullable_string(&step.http_method_or_null),
        json_nullable_string(&step.request_content_type_or_null),
        json_i64_array(&{
            let mut s = step.accepted_statuses.clone();
            s.sort_unstable();
            s
        }),
        json_nullable_string(&step.database_action_or_null),
        json_string(&step.retry_mode),
        json_nullable_string(&step.idempotency_key_source_or_null),
    )
}

pub fn runbook_checksum_payload_json(rb: &Runbook) -> String {
    let mut steps = rb.steps.clone();
    steps.sort_by(|a, b| a.step_id.as_bytes().cmp(b.step_id.as_bytes()));
    let step_json: Vec<String> = steps.iter().map(step_to_checksum_json).collect();
    format!(
        "{{\"runbook_id\":{},\"version\":{},\"plan_rank\":{},\"requires\":{},\"conflicts\":{},\"replaces\":{},\"provides_runbook_ids\":{},\"allowed_api_revisions\":{},\"allowed_database_revisions\":{},\"steps\":[{}]}}",
        json_string(&rb.runbook_id),
        json_string(&rb.version),
        rb.plan_rank,
        json_string_array(&sort_utf8(&rb.requires)),
        json_string_array(&sort_utf8(&rb.conflicts)),
        json_string_array(&sort_utf8(&rb.replaces)),
        json_string_array(&sort_utf8(&rb.provides_runbook_ids)),
        json_string_array(&sort_utf8(&rb.allowed_api_revisions)),
        json_string_array(&sort_utf8(&rb.allowed_database_revisions)),
        step_json.join(","),
    )
}

pub fn compute_runbook_checksum(rb: &Runbook) -> String {
    let text = format!("{}\n", runbook_checksum_payload_json(rb));
    use sha2::{Digest, Sha256};
    let digest = Sha256::digest(text.as_bytes());
    hex::encode(digest)
}

pub fn select_cycle_component(members: &[String]) -> Vec<String> {
    sort_utf8(members)
}

pub fn smallest_scc(components: &[Vec<String>]) -> Vec<String> {
    if components.is_empty() {
        return Vec::new();
    }
    let mut ranked = components.to_vec();
    ranked.sort_by(|a, b| {
        let min_a = a
            .iter()
            .min_by(|x, y| x.as_bytes().cmp(y.as_bytes()))
            .unwrap();
        let min_b = b
            .iter()
            .min_by(|x, y| x.as_bytes().cmp(y.as_bytes()))
            .unwrap();
        min_a.as_bytes().cmp(min_b.as_bytes())
    });
    select_cycle_component(&ranked[0])
}

pub fn unique_array(values: &[String]) -> Result<()> {
    let set: HashSet<&str> = values.iter().map(String::as_str).collect();
    if set.len() != values.len() {
        return Err(FatalInputError::new("duplicate values in unique array"));
    }
    Ok(())
}

pub fn rejection_details_value(details: &crate::model::RejectionDetails) -> Value {
    // Ascending key order per report schema: actual_or_null, cycle_members,
    // expected_or_null, related_ids.
    let mut map = serde_json::Map::new();
    map.insert(
        "actual_or_null".to_string(),
        match &details.actual_or_null {
            Some(v) => Value::String(v.clone()),
            None => Value::Null,
        },
    );
    map.insert(
        "cycle_members".to_string(),
        Value::Array(
            details
                .cycle_members
                .iter()
                .map(|s| Value::String(s.clone()))
                .collect(),
        ),
    );
    map.insert(
        "expected_or_null".to_string(),
        match &details.expected_or_null {
            Some(v) => Value::String(v.clone()),
            None => Value::Null,
        },
    );
    map.insert(
        "related_ids".to_string(),
        Value::Array(
            details
                .related_ids
                .iter()
                .map(|s| Value::String(s.clone()))
                .collect(),
        ),
    );
    Value::Object(map)
}
