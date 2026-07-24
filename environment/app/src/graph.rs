//! Runbook and step dependency graph helpers.
//! Closure, cycle detection, and topological ordering are intentionally incomplete.

#![allow(dead_code)]

use std::collections::HashMap;

use crate::model::Runbook;

/// Placeholder adjacency builder. Does not compute transitive closure.
pub fn adjacency_stub(runbooks: &HashMap<String, Runbook>) -> HashMap<String, Vec<String>> {
    let mut out = HashMap::new();
    for (id, rb) in runbooks {
        out.insert(id.clone(), rb.requires.clone());
    }
    out
}
