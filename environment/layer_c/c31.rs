use crate::d43::join_d;
use crate::types::{HoldoutSummary, OutputDoc, PackView, RunEntry, RunMark, TransitionEntry};
use std::collections::BTreeSet;

pub fn render_c(x0: &[RunMark], x1: &PackView) -> OutputDoc {
    let mut lines = Vec::new();
    for item in x0 {
        if let Some(row) = x1.ledger.iter().find(|row| row.id == item.id) {
            lines.push(join_d(item, row));
        }
    }
    let mut principals = BTreeSet::new();
    for item in x0 {
        principals.insert(item.principal.clone());
    }
    let transitions = principals
        .into_iter()
        .map(|name| TransitionEntry {
            principal: name,
            before: "rev_a".to_string(),
            after: "rev_b".to_string(),
            affected_records: x0.iter().map(|item| item.id.clone()).collect(),
        })
        .collect();
    OutputDoc {
        runs: vec![RunEntry {
            tool: "eta-risk-provenance".to_string(),
            revision: x1.run_id.clone(),
            record_count: x0.len(),
        }],
        records: x0.to_vec(),
        principal_transitions: transitions,
        holdout_summary: HoldoutSummary {
            pinned_split: x1.pinned.clone(),
            review_count: x0.len(),
            held_out_count: x1.held_out.len(),
            held_out_records: Vec::new(),
        },
        statement_evidence: lines,
    }
}
