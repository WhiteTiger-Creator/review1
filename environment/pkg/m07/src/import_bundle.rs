use anyhow::{Context, Result};
use m01::{Catalog, SnapshotRow};
use m02::ContentStore;
use m00::{ImageManifest, SnapshotMeta};
use m03::SnapshotStore;
use std::fs;
use std::path::Path;

pub fn run(root: &str, bundle: &str) -> Result<()> {
    let root_path = Path::new(root);
    fs::create_dir_all(root_path)?;
    let content = ContentStore::new(root_path);
    content.ensure_layout()?;
    let snapshots = SnapshotStore::new(root_path);
    let catalog = Catalog::open(root_path.join("catalog.db"))?;

    let raw = fs::read_to_string(bundle).with_context(|| format!("read bundle {bundle}"))?;
    let manifest: ImageManifest = serde_json::from_str(&raw)?;

    let manifests_dir = root_path.join("manifests");
    fs::create_dir_all(&manifests_dir)?;
    fs::write(
        manifests_dir.join(format!("{}.json", manifest.name)),
        serde_json::to_string_pretty(&manifest)?,
    )?;

    for layer in &manifest.layers {
        if !content.exists(&layer.digest) {
            bail_if_missing_blob(&layer.digest)?;
        }
        catalog.upsert_blob(&layer.digest, layer.size)?;
    }
    catalog.upsert_blob(&manifest.config_digest, 0)?;

    if let Some(snap_path) = Path::new(bundle).parent().map(|p| p.join("snapshot.json")) {
        if snap_path.is_file() {
            let meta: SnapshotMeta = serde_json::from_slice(&fs::read(&snap_path)?)?;
            snapshots.write_snapshot(&meta, &Default::default(), &Default::default())?;
            catalog.upsert_snapshot(&SnapshotRow {
                id: meta.id.clone(),
                parent: meta.parent.clone(),
                digest: meta.digest.clone(),
                kind: meta.kind,
            })?;
        }
    }

    catalog.upsert_image(&manifest, true)?;
    let generation = catalog.store_generation()? + 1;
    catalog.set_store_generation(generation)?;
    Ok(())
}

fn bail_if_missing_blob(digest: &m00::Digest) -> Result<()> {
    anyhow::bail!("missing blob {}", digest);
}
