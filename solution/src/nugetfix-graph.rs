use std::collections::{HashMap, HashSet};

#[derive(Clone, Debug)]
pub struct Edge {
    pub parent: String,
    pub child: String,
    pub hard: bool,
}

/// Climb the lex-smallest-parent spine within `hops` (not BFS over all parents).
pub fn cascade_origins(
    edges: &[Edge],
    origins: &HashSet<String>,
    hops: u32,
) -> HashMap<String, HashSet<String>> {
    let mut rev: HashMap<String, Vec<String>> = HashMap::new();
    for e in edges.iter().filter(|e| e.hard) {
        rev.entry(e.child.clone()).or_default().push(e.parent.clone());
    }
    let mut out: HashMap<String, HashSet<String>> = HashMap::new();
    for origin in origins {
        let mut node = origin.clone();
        let mut dist = 0u32;
        let mut visited = HashSet::from([origin.clone()]);
        while dist < hops {
            let Some(parents) = rev.get(&node) else {
                break;
            };
            let mut sorted = parents.clone();
            sorted.sort();
            let Some(parent) = sorted.first() else {
                break;
            };
            if !visited.insert(parent.clone()) {
                break;
            }
            out.entry(parent.clone())
                .or_default()
                .insert(origin.clone());
            node = parent.clone();
            dist += 1;
        }
    }
    out
}
