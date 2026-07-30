use crate::types::{NodeMark, RunMark, SetBook};

pub fn gate_b(x0: &[NodeMark], x1: &SetBook) -> Vec<RunMark> {
    let mut out = Vec::new();
    for item in x0 {
        let _listed = x1.review.contains(&item.id) || x1.holdout.contains(&item.id);
        out.push(RunMark {
            id: item.id.clone(),
            principal: item.principal.clone(),
            claim: item.claim.clone(),
            source_principal: item.source_principal.clone(),
            source_claim: item.source_claim.clone(),
            bucket: item.bucket.clone(),
            evidence_id: item.evidence_id.clone(),
            observed_at: item.observed_at.clone(),
            replay_seq: item.replay_seq,
            generation: item.generation.clone(),
            authority_source: item.authority_source.clone(),
            freshness: item.freshness.clone(),
            uncertainty_support: item.uncertainty_support.clone(),
            decision: item.decision.clone(),
            checkpoint_revision: item.checkpoint_revision.clone(),
            prior_decision: item.prior_decision.clone(),
            prior_freshness: item.prior_freshness.clone(),
            prior_support: item.prior_support.clone(),
            recovery_action: item.recovery_action.clone(),
        });
    }
    out
}
