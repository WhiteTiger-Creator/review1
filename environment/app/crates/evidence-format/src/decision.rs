use sha2::{Digest, Sha256};

use crate::canonical_cbor::{encode_map, encode_value, validate_cbor};
use crate::edge::{dedupe_edges, merge_paths, EvidenceEdge};
use crate::node::{node_id, sort_nodes, EvidenceNode};

#[derive(Clone, Debug)]
pub struct DecisionDocument {
    pub schema_version: u64,
    pub request_digest: String,
    pub evaluation_epoch: u64,
    pub root_artifact: String,
    pub decision: String,
    pub reason: Option<serde_json::Value>,
    pub artifact_results: Vec<serde_json::Value>,
    pub effective_revocations: Vec<serde_json::Value>,
    pub legacy_evidence_used: Vec<serde_json::Value>,
    pub evidence_digest: String,
}

#[derive(Clone, Debug)]
pub struct EvidenceGraph {
    pub nodes: Vec<EvidenceNode>,
    pub edges: Vec<EvidenceEdge>,
    pub artifact_results: Vec<serde_json::Value>,
}

pub fn build_decision(
    request_digest: &str,
    evaluation_epoch: u64,
    root_artifact: &str,
    artifact_results: Vec<serde_json::Value>,
    evidence_digest: &str,
) -> DecisionDocument {
    DecisionDocument {
        schema_version: 2,
        request_digest: request_digest.to_string(),
        evaluation_epoch,
        root_artifact: root_artifact.to_string(),
        decision: "approve".to_string(),
        reason: None,
        artifact_results,
        effective_revocations: Vec::new(),
        legacy_evidence_used: Vec::new(),
        evidence_digest: evidence_digest.to_string(),
    }
}

pub fn canonical_decision_bytes(decision: &DecisionDocument) -> anyhow::Result<Vec<u8>> {
    let value = serde_json::json!({
        "schema_version": decision.schema_version,
        "request_digest": decision.request_digest,
        "evaluation_epoch": decision.evaluation_epoch,
        "root_artifact": decision.root_artifact,
        "decision": decision.decision,
        "reason": decision.reason,
        "artifact_results": decision.artifact_results,
        "effective_revocations": decision.effective_revocations,
        "legacy_evidence_used": decision.legacy_evidence_used,
        "evidence_digest": decision.evidence_digest,
    });
    Ok(serde_json::to_vec(&value)?)
}

pub fn build_evidence(
    request_digest: &str,
    evaluation_epoch: u64,
    root_artifact: &str,
    nodes: Vec<EvidenceNode>,
    edge_paths: Vec<Vec<EvidenceEdge>>,
    artifact_results: Vec<serde_json::Value>,
) -> anyhow::Result<(EvidenceGraph, Vec<u8>)> {
    let mut node_list = nodes;
    sort_nodes(&mut node_list);
    let edges = dedupe_edges(merge_paths(edge_paths));
    let graph = EvidenceGraph {
        nodes: node_list,
        edges,
        artifact_results: artifact_results.clone(),
    };
    let body = serde_json::json!({
        "schema_version": 1,
        "request_digest": request_digest,
        "evaluation_epoch": evaluation_epoch,
        "root_artifact": root_artifact,
        "nodes": graph.nodes.iter().map(|node| serde_json::json!({
            "id": node.id,
            "kind": node.kind,
            "data": node.data,
        })).collect::<Vec<_>>(),
        "edges": graph.edges.iter().map(|edge| serde_json::json!({
            "from": edge.from,
            "relation": edge.relation,
            "to": edge.to,
            "context": edge.context,
        })).collect::<Vec<_>>(),
        "artifact_results": graph.artifact_results,
    });
    let bytes = encode_value(&body)?;
    validate_cbor(&bytes)?;
    Ok((graph, bytes))
}

pub fn evidence_digest(bytes: &[u8]) -> String {
    format!("sha256:{}", hex::encode(Sha256::digest(bytes)))
}

pub fn make_node(kind: &str, data: serde_json::Value) -> anyhow::Result<EvidenceNode> {
    Ok(EvidenceNode {
        id: node_id(kind, &data)?,
        kind: kind.to_string(),
        data,
    })
}
