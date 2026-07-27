use serde::{Deserialize, Serialize};

use crate::model::{GenerationId, GenerationState, UpgradePhase};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatusReport {
    pub database_path: String,
    pub schema_version: u32,
    pub current_generation: Option<GenerationId>,
    pub published_generation: Option<GenerationId>,
    pub upgrade_phase: UpgradePhase,
    pub upgrade_id: Option<String>,
    pub active_reader_count: usize,
    pub generation_states: Vec<GenerationStatus>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GenerationStatus {
    pub generation_id: i64,
    pub state: GenerationState,
    pub key_id: String,
    pub record_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InspectReport {
    pub generations: Vec<GenerationStatus>,
    pub journal: Option<JournalSummary>,
    pub pins: Vec<PinSummary>,
    pub nonce_reservation_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalSummary {
    pub upgrade_id: String,
    pub phase: UpgradePhase,
    pub source_generation_id: i64,
    pub target_generation_id: i64,
    pub copy_cursor: i64,
    pub reservation_batch: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PinSummary {
    pub token: String,
    pub reader_id: String,
    pub generation_id: i64,
    pub released: bool,
    pub lease_epoch: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub timestamp: String,
    pub operation: String,
    pub upgrade_id: Option<String>,
    pub phase: Option<String>,
    pub outcome: String,
    pub source_generation: Option<i64>,
    pub target_generation: Option<i64>,
    pub reader_count: Option<usize>,
    pub reason_code: String,
}
