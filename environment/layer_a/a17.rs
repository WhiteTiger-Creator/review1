use crate::types::{Checkpoint, FrameSet, NodeMark, RulePack};

pub fn fold_a(x0: &FrameSet, x1: &RulePack, x2: &Checkpoint) -> Vec<NodeMark> {
    let mut out = Vec::new();
    for row in &x0.rows {
        let rule = x1
            .rows
            .iter()
            .find(|item| item.principal == row.principal && item.claim == row.claim);
        let (authority_source, freshness, support, decision) = match rule {
            Some(item) => (
                item.authority_source.clone(),
                "fresh".to_string(),
                "supported".to_string(),
                item.decision.clone(),
            ),
            None => (
                "legacy-default".to_string(),
                "fresh".to_string(),
                "supported".to_string(),
                "allow".to_string(),
            ),
        };
        let prior = x2.rows.iter().find(|item| item.id == row.id);
        out.push(NodeMark {
            id: row.id.clone(),
            principal: row.principal.clone(),
            claim: row.claim.clone(),
            source_principal: row.principal.clone(),
            source_claim: row.claim.clone(),
            bucket: row.bucket.clone(),
            evidence_id: row.evidence_id.clone(),
            observed_at: row.observed_at.clone(),
            replay_seq: row.replay_seq,
            generation: row.generation.clone(),
            authority_source,
            freshness,
            uncertainty_support: support,
            decision,
            checkpoint_revision: prior
                .map(|item| item.revision.clone())
                .unwrap_or_else(|| x2.name.clone()),
            prior_decision: prior
                .map(|item| item.decision.clone())
                .unwrap_or_else(|| "unknown".to_string()),
            prior_freshness: prior
                .map(|item| item.freshness.clone())
                .unwrap_or_else(|| "unknown".to_string()),
            prior_support: prior
                .map(|item| item.support.clone())
                .unwrap_or_else(|| "unknown".to_string()),
            recovery_action: "unchanged".to_string(),
        });
    }
    out
}
