use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Deserialize)]
pub struct FrameSet {
    pub rows: Vec<EventRow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct EventRow {
    pub id: String,
    pub principal: String,
    pub claim: String,
    pub bucket: String,
    pub evidence_id: String,
    pub consent_state: String,
    pub observed_at: String,
    pub replay_seq: u32,
    pub generation: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AliasBook {
    pub principal_aliases: BTreeMap<String, String>,
    pub claim_aliases: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RulePack {
    pub name: String,
    pub rows: Vec<RuleRow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RuleRow {
    pub principal: String,
    pub claim: String,
    pub authority_source: String,
    pub decision: String,
    pub freshness: String,
    pub support: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SetBook {
    pub pinned: String,
    pub review: Vec<String>,
    pub holdout: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct LedgerRow {
    pub id: String,
    pub label: String,
    pub owner: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Checkpoint {
    pub name: String,
    pub rows: Vec<CheckpointRow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct CheckpointRow {
    pub id: String,
    pub principal: String,
    pub evidence_id: String,
    pub revision: String,
    pub decision: String,
    pub freshness: String,
    pub support: String,
}

#[derive(Clone, Debug)]
pub struct NodeMark {
    pub id: String,
    pub principal: String,
    pub claim: String,
    pub source_principal: String,
    pub source_claim: String,
    pub bucket: String,
    pub evidence_id: String,
    pub observed_at: String,
    pub replay_seq: u32,
    pub generation: String,
    pub authority_source: String,
    pub freshness: String,
    pub uncertainty_support: String,
    pub decision: String,
    pub checkpoint_revision: String,
    pub prior_decision: String,
    pub prior_freshness: String,
    pub prior_support: String,
    pub recovery_action: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunMark {
    pub id: String,
    pub principal: String,
    pub claim: String,
    pub source_principal: String,
    pub source_claim: String,
    pub bucket: String,
    pub evidence_id: String,
    pub observed_at: String,
    pub replay_seq: u32,
    pub generation: String,
    pub authority_source: String,
    pub freshness: String,
    pub uncertainty_support: String,
    pub decision: String,
    pub checkpoint_revision: String,
    pub prior_decision: String,
    pub prior_freshness: String,
    pub prior_support: String,
    pub recovery_action: String,
}

#[derive(Clone, Debug)]
pub struct PackView {
    pub run_id: String,
    pub pinned: String,
    pub held_out: Vec<String>,
    pub review_order: Vec<String>,
    pub ledger: Vec<LedgerRow>,
}

#[derive(Clone, Debug, Serialize)]
pub struct OutputDoc {
    pub runs: Vec<RunEntry>,
    pub records: Vec<RunMark>,
    pub principal_transitions: Vec<TransitionEntry>,
    pub holdout_summary: HoldoutSummary,
    pub statement_evidence: Vec<FieldLine>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunEntry {
    pub tool: String,
    pub revision: String,
    pub record_count: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct TransitionEntry {
    pub principal: String,
    pub before: String,
    pub after: String,
    pub affected_records: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct HoldoutSummary {
    pub pinned_split: String,
    pub review_count: usize,
    pub held_out_count: usize,
    pub held_out_records: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct FieldLine {
    pub claim_id: String,
    pub record_id: String,
    pub evidence_id: String,
    pub principal: String,
    pub support: String,
    pub freshness: String,
    pub generation: String,
    pub recovery_action: String,
    pub phrase: String,
}
