use anyhow::{bail, Context, Result};
use m01::Catalog;
use m02::ContentStore;
use m00::ImageManifest;
use serde_json::json;
use m03::SnapshotStore;
use std::fs;
use std::path::Path;
use std::process::Command;

pub fn run(root: &str, image_name: &str, result_path: &str) -> Result<()> {
    let root_path = Path::new(root);
    let catalog = Catalog::open(root_path.join("catalog.db"))?;
    let content = ContentStore::new(root_path);
    let snapshots = SnapshotStore::new(root_path);

    let images = catalog.list_images()?;
    let image = images
        .into_iter()
        .find(|i| i.name == image_name)
        .with_context(|| format!("image {image_name} not found"))?;

    if !catalog.is_runnable(&image, |d| content.exists(d)) {
        bail!("image {image_name} is not runnable");
    }

    let manifest_path = root_path.join(format!("manifests/{image_name}.json"));
    let manifest: ImageManifest =
        serde_json::from_slice(&fs::read(&manifest_path).with_context(|| {
            format!("read manifest {}", manifest_path.display())
        })?)?;

    let chain = snapshots.parent_closure(&manifest.root_snapshot_id)?;
    let probe = Command::new("/app/tools/rootfs-probe")
        .arg("--root")
        .arg(root)
        .arg("--image")
        .arg(image_name)
        .output()
        .context("rootfs probe")?;

    let status = if probe.status.success() {
        "ok"
    } else {
        "failed"
    };

    let result = json!({
        "status": status,
        "image": image_name,
        "rootfs_probe": {
            "exit_code": probe.status.code().unwrap_or(-1),
            "stdout": String::from_utf8_lossy(&probe.stdout).trim(),
            "snapshot_chain": chain,
        }
    });

    if let Some(parent) = Path::new(result_path).parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(result_path, format!("{}\n", serde_json::to_string_pretty(&result)?))?;
    if status != "ok" {
        bail!("rootfs probe failed");
    }
    Ok(())
}
