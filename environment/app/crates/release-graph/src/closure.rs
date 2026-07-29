use crate::artifact::ArtifactRecord;
use crate::traverse::{load_edges, traverse, GraphEdge};

pub fn reachable_closure(root: &str, graph: &serde_json::Value) -> anyhow::Result<Vec<String>> {
    let edges = load_edges(graph)?;
    Ok(traverse(root, &edges))
}

pub fn artifacts_in_closure<'a>(
    closure: &[String],
    artifacts: &'a [ArtifactRecord],
) -> Vec<&'a ArtifactRecord> {
    artifacts
        .iter()
        .filter(|artifact| closure.iter().any(|digest| digest == &artifact.digest))
        .collect()
}
