use crate::digest::Digest;
use crate::snapshot::SnapshotKind;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum InventoryStatus {
    Ok,
    Rejected,
    Partial,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ImageInventory {
    pub name: String,
    pub manifest_digest: Digest,
    pub root_snapshot_id: String,
    pub runnable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SnapshotInventory {
    pub id: String,
    pub parent: Option<String>,
    pub digest: Digest,
    pub kind: SnapshotKind,
    pub reachable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BlobInventory {
    pub digest: Digest,
    pub size: u64,
    pub reachable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LeaseInventory {
    pub lease_id: String,
    pub digest: Digest,
    pub generation: u64,
    pub active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct QuarantineEntry {
    pub path: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct GcInventory {
    pub pending: Vec<Digest>,
    pub reclaimed: Vec<Digest>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct InventoryReport {
    pub schema_version: u32,
    pub status: InventoryStatus,
    pub store_generation: u64,
    pub images: Vec<ImageInventory>,
    pub blobs: Vec<BlobInventory>,
    pub snapshots: Vec<SnapshotInventory>,
    pub leases: Vec<LeaseInventory>,
    pub quarantine: Vec<QuarantineEntry>,
    pub gc: GcInventory,
}

impl InventoryReport {
    pub fn sort_fields(&mut self) {
        self.images.sort_by(|a, b| a.name.cmp(&b.name));
        self.blobs.sort_by(|a, b| a.digest.cmp(&b.digest));
        self.snapshots.sort_by(|a, b| a.id.cmp(&b.id));
        self.leases.sort_by(|a, b| a.lease_id.cmp(&b.lease_id));
        self.quarantine.sort_by(|a, b| a.path.cmp(&b.path));
        self.gc.pending.sort();
        self.gc.reclaimed.sort();
    }
}
