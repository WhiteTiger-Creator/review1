use crate::types::{FieldLine, LedgerRow, RunMark};

pub fn join_d(x0: &RunMark, x1: &LedgerRow) -> FieldLine {
    FieldLine {
        claim_id: x1.label.clone(),
        record_id: x0.id.clone(),
        evidence_id: x0.evidence_id.clone(),
        principal: x0.principal.clone(),
        support: "supported".to_string(),
        freshness: "fresh".to_string(),
        generation: x0.generation.clone(),
        recovery_action: "unchanged".to_string(),
        phrase: format!("{} authority supports precise ETA certainty", x0.principal),
    }
}
