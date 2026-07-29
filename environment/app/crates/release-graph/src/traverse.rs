use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};

#[derive(Clone, Debug)]
pub struct GraphEdge {
    pub from: String,
    pub relation: String,
    pub to: String,
}

pub fn allowed_relations() -> &'static [&'static str] {
    &["contains", "depends-on", "built-from", "packaged-from", "derived-from"]
}

pub fn traverse(root: &str, edges: &[GraphEdge]) -> Vec<String> {
    let allowed: HashSet<&str> = allowed_relations().iter().copied().collect();
    let mut adjacency: HashMap<String, Vec<String>> = HashMap::new();
    for edge in edges {
        if !allowed.contains(edge.relation.as_str()) {
            continue;
        }
        adjacency.entry(edge.from.clone()).or_default().push(edge.to.clone());
    }
    let mut seen = BTreeSet::new();
    let mut queue = VecDeque::new();
    queue.push_back(root.to_string());
    while let Some(node) = queue.pop_front() {
        if !seen.insert(node.clone()) {
            continue;
        }
        if let Some(next) = adjacency.get(&node) {
            for child in next {
                if !seen.contains(child) {
                    queue.push_back(child.clone());
                }
            }
        }
    }
    seen.into_iter().collect()
}

pub fn load_edges(value: &serde_json::Value) -> anyhow::Result<Vec<GraphEdge>> {
    let mut out = Vec::new();
    let items = value["edges"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("graph edges required"))?;
    for item in items {
        out.push(GraphEdge {
            from: item["from"].as_str().unwrap_or("").to_string(),
            relation: item["relation"].as_str().unwrap_or("").to_string(),
            to: item["to"].as_str().unwrap_or("").to_string(),
        });
    }
    Ok(out)
}
