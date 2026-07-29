use crate::canonical_cbor::encode_map;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EvidenceEdge {
    pub from: String,
    pub relation: String,
    pub to: String,
    pub context: serde_json::Value,
}

pub fn sort_edges(edges: &mut [EvidenceEdge]) {
    edges.sort_by(|left, right| {
        left.from
            .cmp(&right.from)
            .then_with(|| left.relation.cmp(&right.relation))
            .then_with(|| left.to.cmp(&right.to))
            .then_with(|| {
                let left_ctx = encode_map(&edge_context_map(&left.context)).unwrap_or_default();
                let right_ctx = encode_map(&edge_context_map(&right.context)).unwrap_or_default();
                left_ctx.cmp(&right_ctx)
            })
    });
}

fn edge_context_map(value: &serde_json::Value) -> Vec<(String, serde_json::Value)> {
    match value.as_object() {
        Some(map) => map
            .iter()
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect(),
        None => Vec::new(),
    }
}

pub fn dedupe_edges(edges: Vec<EvidenceEdge>) -> Vec<EvidenceEdge> {
    let mut out = edges;
    sort_edges(&mut out);
    out.dedup();
    out
}

pub fn merge_paths(paths: Vec<Vec<EvidenceEdge>>) -> Vec<EvidenceEdge> {
    if let Some(first) = paths.into_iter().next() {
        dedupe_edges(first)
    } else {
        Vec::new()
    }
}

