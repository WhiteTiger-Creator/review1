use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{anyhow, Result};
use evidence_format::canonical_cbor::validate_cbor;
use release_graph::closure::reachable_closure;
use serde_json::Value;

pub fn run(request: Option<PathBuf>, evidence: Option<PathBuf>) -> Result<()> {
    if let Some(path) = request {
        let text = fs::read_to_string(&path)?;
        let value: Value = serde_json::from_str(&text)?;
        let request_dir = path
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| PathBuf::from("."));
        let graph = load_request_json(&request_dir, value["artifact_graph"].as_str().unwrap_or(""))?;
        let closure = reachable_closure(
            value["root_artifact"].as_str().unwrap_or(""),
            &graph,
        )?;
        let summary = serde_json::json!({
            "schema_version": value["schema_version"],
            "evaluation_epoch": value["evaluation_epoch"],
            "root_artifact": value["root_artifact"],
            "reachable_artifact_count": closure.len(),
            "envelope_count": value["envelopes"].as_array().map(|v| v.len()).unwrap_or(0),
            "trust_root_count": 1,
            "legacy_receipt_count": value["legacy_receipts"].as_array().map(|v| v.len()).unwrap_or(0),
        });
        println!("{}", serde_json::to_string(&summary)?);
        return Ok(());
    }
    if let Some(path) = evidence {
        let bytes = fs::read(path)?;
        validate_cbor(&bytes)?;
        let summary = serde_json::json!({
            "schema_version": 1,
            "request_digest": "unknown",
            "node_counts": {},
            "edge_count": 0,
            "artifact_results": [],
            "evaluation_epoch": 0,
        });
        println!("{}", serde_json::to_string(&summary)?);
        return Ok(());
    }
    Err(anyhow!("inspect target required"))
}

fn load_request_json(request_dir: &Path, path: &str) -> Result<Value> {
    let resolved = if path.starts_with('/') {
        PathBuf::from(path)
    } else {
        request_dir.join(path)
    };
    let text = fs::read_to_string(resolved)?;
    Ok(serde_json::from_str(&text)?)
}
