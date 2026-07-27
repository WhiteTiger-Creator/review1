pub mod digest;
pub mod inventory;
pub mod manifest;
pub mod snapshot;

pub use digest::{Digest, DigestError};
pub use inventory::{
    BlobInventory, GcInventory, ImageInventory, InventoryReport, InventoryStatus, LeaseInventory,
    QuarantineEntry, SnapshotInventory,
};
pub use manifest::{ImageManifest, LayerDescriptor};
pub use snapshot::{HardlinkIndex, SnapshotKind, SnapshotMeta, WhiteoutIndex};

pub const SCHEMA_VERSION: u32 = 1;
pub const STORE_ROOT_DEFAULT: &str = "/var/lib/mint";
