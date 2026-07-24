use anyhow::{bail, Result};
use m01::{Catalog, GcStage};
use m02::ContentStore;
use m04::LeaseJournal;
use m00::Digest;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, clap::ValueEnum)]
pub enum GcInterruptArg {
    Intent,
    FirstUnlink,
    CatalogCommit,
}

impl From<GcInterruptArg> for GcInterrupt {
    fn from(v: GcInterruptArg) -> Self {
        match v {
            GcInterruptArg::Intent => Self::Intent,
            GcInterruptArg::FirstUnlink => Self::FirstUnlink,
            GcInterruptArg::CatalogCommit => Self::CatalogCommit,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GcInterrupt {
    Intent,
    FirstUnlink,
    CatalogCommit,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GcReport {
    pub reclaimed: Vec<Digest>,
    pub pending: Vec<Digest>,
}

pub struct GcEngine {
    root: PathBuf,
}

impl GcEngine {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    pub fn catalog(&self) -> Result<Catalog> {
        Catalog::open(self.root.join("catalog.db"))
    }

    pub fn run(&self, interrupt_after: Option<GcInterrupt>) -> Result<GcReport> {
        let catalog = self.catalog()?;
        let content = ContentStore::new(&self.root);
        let journal = LeaseJournal::new(&self.root);
        let lease_state = journal.replay()?;
        let reach = catalog.compute_reachability()?;
        let mut reclaimed = Vec::new();
        let mut pending = Vec::new();

        let blobs = catalog.list_blobs()?;
        let mut targets: HashSet<Digest> = HashSet::new();
        for blob in &blobs {
            if reach.blob_reachable(&blob.digest) || lease_state.is_leased(&blob.digest) {
                continue;
            }
            targets.insert(blob.digest.clone());
            catalog.record_gc_intent(&blob.digest, GcStage::Planned)?;
        }

        if interrupt_after == Some(GcInterrupt::Intent) {
            return Ok(GcReport {
                reclaimed,
                pending: targets.into_iter().collect(),
            });
        }

        let mut first_unlink_done = false;
        for digest in targets.iter() {
            if content.exists(digest) {
                content.unlink(digest)?;
                catalog.record_gc_intent(digest, GcStage::Unlinked)?;
                reclaimed.push(digest.clone());
                if !first_unlink_done {
                    first_unlink_done = true;
                    if interrupt_after == Some(GcInterrupt::FirstUnlink) {
                        pending = targets.iter().filter(|d| !reclaimed.contains(d)).cloned().collect();
                        pending.sort();
                        reclaimed.sort();
                        return Ok(GcReport { reclaimed, pending });
                    }
                }
            }
        }

        let intents = catalog.list_gc_intent()?;
        for (digest, _stage) in intents {
            if lease_state.is_leased(&digest) {
                pending.push(digest);
                continue;
            }
            catalog.delete_blob(&digest)?;
            catalog.clear_gc_intent(&digest)?;
            if !reclaimed.contains(&digest) {
                reclaimed.push(digest);
            }
        }

        if interrupt_after == Some(GcInterrupt::CatalogCommit) {
            pending.sort();
            reclaimed.sort();
            return Ok(GcReport { reclaimed, pending });
        }

        reclaimed.sort();
        pending.sort();
        Ok(GcReport { reclaimed, pending })
    }

    pub fn release_lease(&self, lease_id: &str, generation: u64) -> Result<()> {
        let journal = LeaseJournal::new(&self.root);
        let mut state = journal.replay()?;
        state.validate_release(lease_id, generation)?;
        state.active.retain(|(id, _, g)| !(id == lease_id && *g <= generation));
        journal.release(lease_id, generation)?;
        let catalog = self.catalog()?;
        for (id, digest, lease_generation, _) in catalog.list_leases()? {
            if id == lease_id && lease_generation <= generation {
                catalog.record_lease(&id, &digest, lease_generation, false)?;
            }
        }
        Ok(())
    }

    pub fn acquire_lease(&self, lease_id: &str, digest: &Digest, generation: u64) -> Result<()> {
        let journal = LeaseJournal::new(&self.root);
        journal.acquire(lease_id, digest, generation)?;
        let catalog = self.catalog()?;
        catalog.record_lease(lease_id, digest, generation, true)?;
        Ok(())
    }
}

pub fn load_gc_config(path: &Path) -> Result<GcConfig> {
    let raw = std::fs::read_to_string(path)?;
    Ok(toml::from_str(&raw)?)
}

#[derive(Debug, Clone, Deserialize)]
pub struct GcConfig {
    pub batch_size: usize,
    pub respect_leases: bool,
}

impl Default for GcConfig {
    fn default() -> Self {
        Self {
            batch_size: 64,
            respect_leases: true,
        }
    }
}

pub fn validate_gc_config(cfg: &GcConfig) -> Result<()> {
    if cfg.batch_size == 0 {
        bail!("batch_size must be positive");
    }
    Ok(())
}
