use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct RecordVersion {
    pub epoch: u64,
    pub counter: u64,
}

impl RecordVersion {
    pub fn new(epoch: u64, counter: u64) -> Self {
        Self { epoch, counter }
    }

    pub fn canonical_key(&self) -> (u64, u64) {
        (self.epoch, self.counter)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogicalRecord {
    pub record_id: String,
    pub payload: String,
    pub version: RecordVersion,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct GenerationId(pub i64);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum GenerationState {
    Copying,
    Validated,
    Published,
    PinsReconciled,
    CleanupPending,
    Complete,
}

impl GenerationState {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Copying => "copying",
            Self::Validated => "validated",
            Self::Published => "published",
            Self::PinsReconciled => "pins_reconciled",
            Self::CleanupPending => "cleanup_pending",
            Self::Complete => "complete",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "copying" => Some(Self::Copying),
            "validated" => Some(Self::Validated),
            "published" => Some(Self::Published),
            "pins_reconciled" => Some(Self::PinsReconciled),
            "cleanup_pending" => Some(Self::CleanupPending),
            "complete" => Some(Self::Complete),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum UpgradePhase {
    Idle,
    Reserved,
    Copying,
    Copied,
    Validated,
    Published,
    PinsReconciled,
    CleanupPending,
    Complete,
}

impl UpgradePhase {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Idle => "idle",
            Self::Reserved => "reserved",
            Self::Copying => "copying",
            Self::Copied => "copied",
            Self::Validated => "validated",
            Self::Published => "published",
            Self::PinsReconciled => "pins_reconciled",
            Self::CleanupPending => "cleanup_pending",
            Self::Complete => "complete",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "idle" => Some(Self::Idle),
            "reserved" => Some(Self::Reserved),
            "copying" => Some(Self::Copying),
            "copied" => Some(Self::Copied),
            "validated" => Some(Self::Validated),
            "published" => Some(Self::Published),
            "pins_reconciled" => Some(Self::PinsReconciled),
            "cleanup_pending" => Some(Self::CleanupPending),
            "complete" => Some(Self::Complete),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReaderSnapshot {
    pub token: String,
    pub reader_id: String,
    pub generation_id: GenerationId,
    pub lease_epoch: u64,
    pub opened_seq: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VaultConfig {
    pub database_path: String,
    pub audit_path: String,
    pub batch_size: usize,
    pub active_key_id: String,
    pub supported_legacy_versions: Vec<u32>,
}

impl Default for VaultConfig {
    fn default() -> Self {
        Self {
            database_path: "/app/state/store.db".into(),
            audit_path: "/app/state/store.audit.jsonl".into(),
            batch_size: 3,
            active_key_id: "key-current".into(),
            supported_legacy_versions: vec![1, 2],
        }
    }
}

pub const FAILPOINT_EXIT_CODE: i32 = 75;

pub const FAILPOINTS: &[&str] = &[
    "after-reservation",
    "after-partial-copy",
    "after-copy-complete",
    "after-target-validation",
    "after-publication",
    "after-pin-reconciliation",
    "during-cleanup",
];

pub fn check_failpoint(name: &str) -> Result<(), i32> {
    match std::env::var("KSEAL_FAILPOINT") {
        Ok(fp) if fp == name => Err(FAILPOINT_EXIT_CODE),
        _ => Ok(()),
    }
}
