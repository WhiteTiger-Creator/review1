use anyhow::{anyhow, Result};
use serde_json::Value;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PayloadKind {
    Attestation,
    Delegation,
    Revocation,
    Migration,
}

pub fn validate_payload_type(payload_type: &str) -> Result<PayloadKind> {
    match payload_type {
        "application/vnd.dac.attestation+json" => Ok(PayloadKind::Attestation),
        "application/vnd.dac.delegation+json" => Ok(PayloadKind::Delegation),
        "application/vnd.dac.revocation+json" => Ok(PayloadKind::Revocation),
        "application/vnd.dac.migration+json" => Ok(PayloadKind::Migration),
        other => Err(anyhow!("unsupported payload type: {other}")),
    }
}

pub fn parse_payload(value: &Value) -> Result<(PayloadKind, Value)> {
    let payload_type = value
        .get("payload_type")
        .and_then(|v| v.as_str())
        .unwrap_or("application/vnd.dac.attestation+json");
    Ok((validate_payload_type(payload_type)?, value.clone()))
}

pub fn attestation_subjects(payload: &Value) -> Vec<String> {
    payload["subjects"]
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}
