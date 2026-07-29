use std::fs;
use std::path::PathBuf;

use anyhow::{anyhow, Result};
use decision_publish::validate_outputs;
use envelope_format::envelope_digest;
use evidence_format::canonical_cbor::validate_cbor;
use evidence_format::decision::DecisionDocument;
use serde_json::Value;

pub fn run(request: PathBuf, decision: PathBuf, evidence: PathBuf) -> Result<()> {
    let request_text = fs::read_to_string(request)?;
    let request: Value = serde_json::from_str(&request_text)?;
    let decision_text = fs::read_to_string(decision)?;
    let decision_value: Value = serde_json::from_str(&decision_text)?;
    let evidence_bytes = fs::read(evidence)?;
    validate_cbor(&evidence_bytes)?;
    let request_digest = envelope_digest(request_text.trim_end().as_bytes());
    if decision_value["request_digest"].as_str() != Some(request_digest.as_str()) {
        anyhow::bail!("request digest mismatch");
    }
    let document = DecisionDocument {
        schema_version: decision_value["schema_version"].as_u64().unwrap_or(2),
        request_digest: decision_value["request_digest"]
            .as_str()
            .unwrap_or("")
            .to_string(),
        evaluation_epoch: decision_value["evaluation_epoch"].as_u64().unwrap_or(0),
        root_artifact: decision_value["root_artifact"].as_str().unwrap_or("").to_string(),
        decision: decision_value["decision"].as_str().unwrap_or("reject").to_string(),
        reason: decision_value.get("reason").cloned(),
        artifact_results: decision_value["artifact_results"]
            .as_array()
            .cloned()
            .unwrap_or_default(),
        effective_revocations: decision_value["effective_revocations"]
            .as_array()
            .cloned()
            .unwrap_or_default(),
        legacy_evidence_used: decision_value["legacy_evidence_used"]
            .as_array()
            .cloned()
            .unwrap_or_default(),
        evidence_digest: decision_value["evidence_digest"]
            .as_str()
            .unwrap_or("")
            .to_string(),
    };
    validate_outputs(&document, &evidence_bytes)?;
    Ok(())
}
