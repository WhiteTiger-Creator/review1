use anyhow::{bail, Context, Result};
use m02::{write_atomic, ContentStore};
use m00::{Digest, HardlinkIndex, SnapshotKind, SnapshotMeta, WhiteoutIndex};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

pub struct SnapshotStore {
    root: PathBuf,
    content: ContentStore,
}

impl SnapshotStore {
    pub fn new(store_root: impl AsRef<Path>) -> Self {
        let root = store_root.as_ref().to_path_buf();
        Self {
            content: ContentStore::new(&root),
            root,
        }
    }

    pub fn snapshots_dir(&self) -> PathBuf {
        self.root.join("snapshots")
    }

    pub fn snapshot_dir(&self, id: &str) -> PathBuf {
        self.snapshots_dir().join(id)
    }

    pub fn meta_path(&self, id: &str) -> PathBuf {
        self.snapshot_dir(id).join(".rstore/snapshot.json")
    }

    pub fn whiteout_path(&self, id: &str) -> PathBuf {
        self.snapshot_dir(id).join(".rstore/whiteout.json")
    }

    pub fn hardlink_path(&self, id: &str) -> PathBuf {
        self.snapshot_dir(id).join(".rstore/hardlink.json")
    }

    pub fn write_snapshot(
        &self,
        meta: &SnapshotMeta,
        whiteout: &WhiteoutIndex,
        hardlink: &HardlinkIndex,
    ) -> Result<()> {
        self.validate_parent_chain(meta)?;
        let dir = self.snapshot_dir(&meta.id).join(".rstore");
        fs::create_dir_all(&dir)?;
        write_atomic(
            &self.meta_path(&meta.id),
            serde_json::to_vec_pretty(meta)?.as_slice(),
        )?;
        write_atomic(
            &self.whiteout_path(&meta.id),
            serde_json::to_vec_pretty(whiteout)?.as_slice(),
        )?;
        write_atomic(
            &self.hardlink_path(&meta.id),
            serde_json::to_vec_pretty(hardlink)?.as_slice(),
        )?;
        Ok(())
    }

    pub fn validate_parent_chain(&self, meta: &SnapshotMeta) -> Result<()> {
        if meta.kind == SnapshotKind::Marker {
            return Ok(());
        }
        if let Some(parent) = &meta.parent {
            if !self.meta_path(parent).is_file() {
                bail!("missing parent snapshot {parent}");
            }
        }
        Ok(())
    }

    pub fn load_meta(&self, id: &str) -> Result<SnapshotMeta> {
        let raw = fs::read_to_string(self.meta_path(id))
            .with_context(|| format!("read snapshot meta {id}"))?;
        Ok(serde_json::from_str(&raw)?)
    }

    pub fn load_whiteout(&self, id: &str) -> Result<WhiteoutIndex> {
        let path = self.whiteout_path(id);
        if !path.is_file() {
            return Ok(WhiteoutIndex::default());
        }
        Ok(serde_json::from_str(&fs::read_to_string(path)?)?)
    }

    pub fn load_hardlink(&self, id: &str) -> Result<HardlinkIndex> {
        let path = self.hardlink_path(id);
        if !path.is_file() {
            return Ok(HardlinkIndex::default());
        }
        Ok(serde_json::from_str(&fs::read_to_string(path)?)?)
    }

    pub fn list_ids(&self) -> Result<Vec<String>> {
        let mut ids = Vec::new();
        let dir = self.snapshots_dir();
        if !dir.exists() {
            return Ok(ids);
        }
        for entry in WalkDir::new(&dir).min_depth(1).max_depth(1) {
            let entry = entry?;
            if entry.file_type().is_dir() {
                ids.push(entry.file_name().to_string_lossy().into_owned());
            }
        }
        ids.sort();
        Ok(ids)
    }

    pub fn parent_closure(&self, root_id: &str) -> Result<Vec<String>> {
        let mut chain = Vec::new();
        let mut seen = HashSet::new();
        let mut current = Some(root_id.to_string());
        while let Some(id) = current {
            if !seen.insert(id.clone()) {
                bail!("cycle in snapshot parent chain at {id}");
            }
            chain.push(id.clone());
            let meta = self.load_meta(&id)?;
            current = meta.parent;
        }
        Ok(chain)
    }

    pub fn verify_indexes(&self, id: &str) -> Result<()> {
        let _whiteout = self.load_whiteout(id)?;
        let hardlink = self.load_hardlink(id)?;
        for link in &hardlink.links {
            if link.source.is_empty() || link.target.is_empty() {
                bail!("invalid hardlink entry in {id}");
            }
        }
        Ok(())
    }

    pub fn content_store(&self) -> &ContentStore {
        &self.content
    }
}
