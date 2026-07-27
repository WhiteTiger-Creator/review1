use anyhow::{bail, Context, Result};
use m01::{Catalog, SnapshotRow};
use m02::ContentStore;
use m04::LeaseJournal;
use m00::{
    BlobInventory, GcInventory, ImageInventory, InventoryReport, InventoryStatus, LeaseInventory,
    QuarantineEntry, SnapshotInventory, SCHEMA_VERSION,
};
use serde::{Deserialize, Serialize};
use m03::SnapshotStore;
use std::collections::HashSet;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, clap::ValueEnum)]
pub enum RecoveryInterruptArg {
    Validation,
    CatalogStage,
}

impl From<RecoveryInterruptArg> for RecoveryInterrupt {
    fn from(v: RecoveryInterruptArg) -> Self {
        match v {
            RecoveryInterruptArg::Validation => Self::Validation,
            RecoveryInterruptArg::CatalogStage => Self::CatalogStage,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecoveryInterrupt {
    Validation,
    CatalogStage,
}

pub struct RecoveryEngine {
    root: PathBuf,
}

impl RecoveryEngine {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    pub fn recover(
        &self,
        output: &Path,
        interrupt_after: Option<RecoveryInterrupt>,
    ) -> Result<InventoryReport> {
        let catalog = Catalog::open(self.root.join("catalog.db"))?;
        let snapshots = SnapshotStore::new(&self.root);
        let content = ContentStore::new(&self.root);
        let journal = LeaseJournal::new(&self.root);

        let on_disk_snapshots = snapshots.list_ids()?;
        let mut tampered = false;

        for id in &on_disk_snapshots {
            if let Ok(meta) = snapshots.load_meta(id) {
                if content.verify_blob(&meta.digest).is_err() {
                    tampered = true;
                }
                if snapshots.verify_indexes(id).is_err() {
                    tampered = true;
                }
            } else {
                tampered = true;
            }
        }

        if tampered {
            let report = self.build_rejected_report(&catalog)?;
            self.write_report(output, &report)?;
            return Ok(report);
        }

        if interrupt_after == Some(RecoveryInterrupt::Validation) {
            let report = self.build_partial_report(&catalog, &content, &snapshots, &journal)?;
            self.write_report(output, &report)?;
            return Ok(report);
        }

        for id in &on_disk_snapshots {
            if catalog.get_snapshot(id)?.is_none() {
                if let Ok(meta) = snapshots.load_meta(id) {
                    catalog.upsert_snapshot(&SnapshotRow {
                        id: meta.id.clone(),
                        parent: meta.parent.clone(),
                        digest: meta.digest.clone(),
                        kind: meta.kind,
                    })?;
                }
            }
        }

        if interrupt_after == Some(RecoveryInterrupt::CatalogStage) {
            let report = self.build_partial_report(&catalog, &content, &snapshots, &journal)?;
            self.write_report(output, &report)?;
            return Ok(report);
        }

        let lease_state = journal.replay()?;
        let reach = catalog.compute_reachability()?;
        let mut report = InventoryReport {
            schema_version: SCHEMA_VERSION,
            status: InventoryStatus::Ok,
            store_generation: catalog.store_generation()?,
            images: Vec::new(),
            blobs: Vec::new(),
            snapshots: Vec::new(),
            leases: Vec::new(),
            quarantine: Vec::new(),
            gc: GcInventory::default(),
        };

        for image in catalog.list_images()? {
            let runnable = catalog.is_runnable(&image, |d| content.exists(d));
            report.images.push(ImageInventory {
                name: image.name,
                manifest_digest: image.manifest_digest,
                root_snapshot_id: image.root_snapshot_id,
                runnable,
            });
        }

        for blob in catalog.list_blobs()? {
            let digest = blob.digest.clone();
            let reachable = reach.blob_reachable(&digest);
            report.blobs.push(BlobInventory {
                digest,
                size: blob.size,
                reachable,
            });
        }

        for snap in catalog.list_snapshots()? {
            let snap_id = snap.id.clone();
            report.snapshots.push(SnapshotInventory {
                id: snap_id.clone(),
                parent: snap.parent,
                digest: snap.digest,
                kind: snap.kind,
                reachable: reach.snapshot_reachable(&snap_id),
            });
        }

        for (lease_id, digest, generation, active) in catalog.list_leases()? {
            let journal_active = lease_state.active.iter().any(|(id, _, _)| id == &lease_id);
            report.leases.push(LeaseInventory {
                lease_id,
                digest,
                generation,
                active: active && journal_active,
            });
        }

        let intents = catalog.list_gc_intent()?;
        for (digest, _) in intents {
            report.gc.pending.push(digest);
        }
        report.gc.pending.sort();

        report.sort_fields();
        self.write_report(output, &report)?;
        Ok(report)
    }

    fn build_rejected_report(&self, catalog: &Catalog) -> Result<InventoryReport> {
        let mut report = InventoryReport {
            schema_version: SCHEMA_VERSION,
            status: InventoryStatus::Rejected,
            store_generation: catalog.store_generation().unwrap_or(0),
            images: Vec::new(),
            blobs: Vec::new(),
            snapshots: Vec::new(),
            leases: Vec::new(),
            quarantine: vec![QuarantineEntry {
                path: self.root.display().to_string(),
                reason: "tampered or irreconcilable evidence".into(),
            }],
            gc: GcInventory::default(),
        };
        report.sort_fields();
        Ok(report)
    }

    fn build_partial_report(
        &self,
        catalog: &Catalog,
        content: &ContentStore,
        snapshots: &SnapshotStore,
        journal: &LeaseJournal,
    ) -> Result<InventoryReport> {
        let _ = (content, snapshots, journal);
        let mut report = InventoryReport {
            schema_version: SCHEMA_VERSION,
            status: InventoryStatus::Partial,
            store_generation: catalog.store_generation()?,
            images: Vec::new(),
            blobs: Vec::new(),
            snapshots: Vec::new(),
            leases: Vec::new(),
            quarantine: Vec::new(),
            gc: GcInventory::default(),
        };
        report.sort_fields();
        Ok(report)
    }

    fn write_report(&self, output: &Path, report: &InventoryReport) -> Result<()> {
        if let Some(parent) = output.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let mut json = serde_json::to_string_pretty(report)?;
        json.push('\n');
        std::fs::write(output, json)?;
        Ok(())
    }

    pub fn verify_store(&self) -> Result<()> {
        let catalog = Catalog::open(self.root.join("catalog.db"))?;
        let content = ContentStore::new(&self.root);
        let snapshots = SnapshotStore::new(&self.root);
        let mut seen = HashSet::new();
        for id in snapshots.list_ids()? {
            let meta = snapshots.load_meta(&id)?;
            if !seen.insert(meta.id.clone()) {
                bail!("duplicate snapshot id {}", meta.id);
            }
            content.verify_blob(&meta.digest)?;
            snapshots.verify_indexes(&id)?;
        }
        let _reach = catalog.compute_reachability()?;
        Ok(())
    }
}

pub fn load_recovery_config(path: &Path) -> Result<RecoveryConfig> {
    let raw = std::fs::read_to_string(path)?;
    Ok(toml::from_str(&raw)?)
}

#[derive(Debug, Clone, Deserialize)]
pub struct RecoveryConfig {
    pub allow_catalog_rebuild: bool,
    pub strict_tamper_check: bool,
}

impl Default for RecoveryConfig {
    fn default() -> Self {
        Self {
            allow_catalog_rebuild: true,
            strict_tamper_check: true,
        }
    }
}
