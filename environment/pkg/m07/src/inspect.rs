use anyhow::{Context, Result};
use m01::Catalog;
use serde_json::json;
use std::path::Path;

pub fn run(root: &str) -> Result<()> {
    let catalog = Catalog::open(Path::new(root).join("catalog.db"))?;
    let images = catalog.list_images()?;
    let blobs = catalog.list_blobs()?;
    let snapshots = catalog.list_snapshots()?;
    let summary = json!({
        "store_generation": catalog.store_generation()?,
        "image_count": images.len(),
        "blob_count": blobs.len(),
        "snapshot_count": snapshots.len(),
        "images": images.iter().map(|i| &i.name).collect::<Vec<_>>(),
    });
    println!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(())
}
