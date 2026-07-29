use crate::canonical_cbor::encode_map;
use sha2::{Digest, Sha256};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EvidenceNode {
    pub id: String,
    pub kind: String,
    pub data: serde_json::Value,
}

pub fn node_id(kind: &str, data: &serde_json::Value) -> anyhow::Result<String> {
    let body = serde_json::json!({"kind": kind, "data": data});
    let pairs = vec![
        ("kind".to_string(), body["kind"].clone()),
        ("data".to_string(), body["data"].clone()),
    ];
    let encoded = encode_map(&pairs)?;
    Ok(format!("sha256:{}", hex::encode(Sha256::digest(encoded))))
}

pub fn sort_nodes(nodes: &mut [EvidenceNode]) {
    nodes.sort_by(|left, right| left.id.cmp(&right.id));
}
