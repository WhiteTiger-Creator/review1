mod migrations;
mod reachability;

use anyhow::{Context, Result};
use migrations::apply_migrations;
use m00::{Digest, ImageManifest, SnapshotKind};
use rusqlite::{params, Connection, OptionalExtension};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

pub use reachability::Reachability;

pub struct Catalog {
    path: PathBuf,
    conn: Connection,
}

#[derive(Debug, Clone)]
pub struct ImageRow {
    pub name: String,
    pub manifest_digest: Digest,
    pub root_snapshot_id: String,
    pub runnable: bool,
}

#[derive(Debug, Clone)]
pub struct SnapshotRow {
    pub id: String,
    pub parent: Option<String>,
    pub digest: Digest,
    pub kind: SnapshotKind,
}

#[derive(Debug, Clone)]
pub struct BlobRow {
    pub digest: Digest,
    pub size: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GcStage {
    Planned,
    Unlinked,
    CatalogRemoved,
}

impl GcStage {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Planned => "planned",
            Self::Unlinked => "unlinked",
            Self::CatalogRemoved => "catalog_removed",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "planned" => Some(Self::Planned),
            "unlinked" => Some(Self::Unlinked),
            "catalog_removed" => Some(Self::CatalogRemoved),
            _ => None,
        }
    }
}

impl Catalog {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref().to_path_buf();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let conn = Connection::open(&path).context("open catalog.db")?;
        conn.execute_batch("PRAGMA foreign_keys = ON;")?;
        apply_migrations(&conn)?;
        Ok(Self { path, conn })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn conn(&self) -> &Connection {
        &self.conn
    }

    pub fn store_generation(&self) -> Result<u64> {
        Ok(self
            .get_meta("store_generation")?
            .unwrap_or("0".into())
            .parse()?)
    }

    pub fn set_store_generation(&self, generation: u64) -> Result<()> {
        self.set_meta("store_generation", &generation.to_string())
    }

    pub fn get_meta(&self, key: &str) -> Result<Option<String>> {
        self.conn
            .query_row(
                "SELECT value FROM store_meta WHERE key = ?1",
                params![key],
                |row| row.get(0),
            )
            .optional()
            .context("get meta")
    }

    pub fn set_meta(&self, key: &str, value: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO store_meta(key, value) VALUES(?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![key, value],
        )?;
        Ok(())
    }

    pub fn upsert_image(&self, manifest: &ImageManifest, runnable: bool) -> Result<()> {
        self.conn.execute(
            "INSERT INTO images(name, manifest_digest, root_snapshot_id, runnable)
             VALUES(?1, ?2, ?3, ?4)
             ON CONFLICT(name) DO UPDATE SET
               manifest_digest = excluded.manifest_digest,
               root_snapshot_id = excluded.root_snapshot_id,
               runnable = excluded.runnable",
            params![
                manifest.name,
                manifest.config_digest.as_str(),
                manifest.root_snapshot_id,
                runnable as i64
            ],
        )?;
        Ok(())
    }

    pub fn list_images(&self) -> Result<Vec<ImageRow>> {
        let mut stmt = self.conn.prepare(
            "SELECT name, manifest_digest, root_snapshot_id, runnable FROM images ORDER BY name",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(ImageRow {
                name: row.get(0)?,
                manifest_digest: Digest::from_hex(row.get::<_, String>(1)?.as_str()).unwrap(),
                root_snapshot_id: row.get(2)?,
                runnable: row.get::<_, i64>(3)? != 0,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().context("list images")
    }

    pub fn upsert_snapshot(&self, row: &SnapshotRow) -> Result<()> {
        let kind = match row.kind {
            SnapshotKind::Full => "full",
            SnapshotKind::Marker => "marker",
        };
        self.conn.execute(
            "INSERT INTO snapshots(id, parent_id, digest, kind)
             VALUES(?1, ?2, ?3, ?4)
             ON CONFLICT(id) DO UPDATE SET
               parent_id = excluded.parent_id,
               digest = excluded.digest,
               kind = excluded.kind",
            params![row.id, row.parent, row.digest.as_str(), kind],
        )?;
        Ok(())
    }

    pub fn get_snapshot(&self, id: &str) -> Result<Option<SnapshotRow>> {
        self.conn
            .query_row(
                "SELECT id, parent_id, digest, kind FROM snapshots WHERE id = ?1",
                params![id],
                |row| {
                    let kind: String = row.get(3)?;
                    Ok(SnapshotRow {
                        id: row.get(0)?,
                        parent: row.get(1)?,
                        digest: Digest::from_hex(row.get::<_, String>(2)?.as_str()).unwrap(),
                        kind: if kind == "marker" {
                            SnapshotKind::Marker
                        } else {
                            SnapshotKind::Full
                        },
                    })
                },
            )
            .optional()
            .context("get snapshot")
    }

    pub fn list_snapshots(&self) -> Result<Vec<SnapshotRow>> {
        let mut stmt =
            self.conn
                .prepare("SELECT id, parent_id, digest, kind FROM snapshots ORDER BY id")?;
        let rows = stmt.query_map([], |row| {
            let kind: String = row.get(3)?;
            Ok(SnapshotRow {
                id: row.get(0)?,
                parent: row.get(1)?,
                digest: Digest::from_hex(row.get::<_, String>(2)?.as_str()).unwrap(),
                kind: if kind == "marker" {
                    SnapshotKind::Marker
                } else {
                    SnapshotKind::Full
                },
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().context("list snapshots")
    }

    pub fn delete_snapshot(&self, id: &str) -> Result<()> {
        self.conn
            .execute("DELETE FROM snapshots WHERE id = ?1", params![id])?;
        Ok(())
    }

    pub fn upsert_blob(&self, digest: &Digest, size: u64) -> Result<()> {
        self.conn.execute(
            "INSERT INTO blobs(digest, size) VALUES(?1, ?2)
             ON CONFLICT(digest) DO UPDATE SET size = excluded.size",
            params![digest.as_str(), size],
        )?;
        Ok(())
    }

    pub fn list_blobs(&self) -> Result<Vec<BlobRow>> {
        let mut stmt = self
            .conn
            .prepare("SELECT digest, size FROM blobs ORDER BY digest")?;
        let rows = stmt.query_map([], |row| {
            Ok(BlobRow {
                digest: Digest::from_hex(row.get::<_, String>(0)?.as_str()).unwrap(),
                size: row.get(1)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().context("list blobs")
    }

    pub fn delete_blob(&self, digest: &Digest) -> Result<()> {
        self.conn
            .execute("DELETE FROM blobs WHERE digest = ?1", params![digest.as_str()])?;
        Ok(())
    }

    pub fn record_gc_intent(&self, digest: &Digest, stage: GcStage) -> Result<()> {
        self.conn.execute(
            "INSERT INTO gc_intent(digest, stage) VALUES(?1, ?2)
             ON CONFLICT(digest) DO UPDATE SET stage = excluded.stage",
            params![digest.as_str(), stage.as_str()],
        )?;
        Ok(())
    }

    pub fn list_gc_intent(&self) -> Result<HashMap<Digest, GcStage>> {
        let mut stmt = self
            .conn
            .prepare("SELECT digest, stage FROM gc_intent ORDER BY digest")?;
        let rows = stmt.query_map([], |row| {
            let digest = Digest::from_hex(row.get::<_, String>(0)?.as_str()).unwrap();
            let stage = GcStage::parse(&row.get::<_, String>(1)?).unwrap();
            Ok((digest, stage))
        })?;
        rows.collect::<Result<HashMap<_, _>, _>>().context("list gc intent")
    }

    pub fn clear_gc_intent(&self, digest: &Digest) -> Result<()> {
        self.conn
            .execute("DELETE FROM gc_intent WHERE digest = ?1", params![digest.as_str()])?;
        Ok(())
    }

    pub fn record_lease(
        &self,
        lease_id: &str,
        digest: &Digest,
        generation: u64,
        active: bool,
    ) -> Result<()> {
        self.conn.execute(
            "INSERT INTO leases(lease_id, digest, generation, active)
             VALUES(?1, ?2, ?3, ?4)
             ON CONFLICT(lease_id) DO UPDATE SET
               digest = excluded.digest,
               generation = excluded.generation,
               active = excluded.active",
            params![lease_id, digest.as_str(), generation, active as i64],
        )?;
        Ok(())
    }

    pub fn list_leases(&self) -> Result<Vec<(String, Digest, u64, bool)>> {
        let mut stmt = self.conn.prepare(
            "SELECT lease_id, digest, generation, active FROM leases ORDER BY lease_id",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                Digest::from_hex(row.get::<_, String>(1)?.as_str()).unwrap(),
                row.get::<_, u64>(2)?,
                row.get::<_, i64>(3)? != 0,
            ))
        })?;
        rows.collect::<Result<Vec<_>, _>>().context("list leases")
    }

    pub fn compute_reachability(&self) -> Result<Reachability> {
        let images = self.list_images()?;
        let mut reachable_blobs = HashSet::new();
        for image in &images {
            if let Ok(manifest_bytes) = std::fs::read(
                self.path()
                    .parent()
                    .unwrap()
                    .join(format!("manifests/{}.json", image.name)),
            ) {
                if let Ok(manifest) = serde_json::from_slice::<ImageManifest>(&manifest_bytes) {
                    for layer in &manifest.layers {
                        reachable_blobs.insert(layer.digest.clone());
                    }
                    reachable_blobs.insert(manifest.config_digest.clone());
                }
            }
        }
        let snapshots: HashSet<String> = images
            .iter()
            .map(|i| i.root_snapshot_id.clone())
            .collect();
        Ok(Reachability {
            blobs: reachable_blobs,
            snapshots,
        })
    }

    pub fn is_runnable(&self, image: &ImageRow, content_exists: impl Fn(&Digest) -> bool) -> bool {
        content_exists(&image.manifest_digest)
    }
}
