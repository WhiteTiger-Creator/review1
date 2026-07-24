use anyhow::Result;
use std::collections::{HashMap, HashSet};
use std::path::Path;

#[derive(Debug, Clone, serde::Deserialize)]
pub struct ManifestFile {
    pub name: String,
    pub config_digest: String,
    pub layers: Vec<Layer>,
    pub root_snapshot_id: String,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct Layer {
    pub digest: String,
}

#[derive(Debug, Clone, serde::Deserialize)]
pub struct SnapshotMeta {
    pub id: String,
    pub parent: Option<String>,
    pub digest: String,
    pub kind: String,
}

pub fn expected_reachability(root: &Path) -> Result<(HashSet<String>, HashSet<String>)> {
    let manifests_dir = root.join("manifests");
    let mut blob_digests = HashSet::new();
    let mut snapshot_ids = HashSet::new();

    if manifests_dir.is_dir() {
        for entry in std::fs::read_dir(&manifests_dir)? {
            let entry = entry?;
            let manifest: ManifestFile = serde_json::from_slice(&std::fs::read(entry.path())?)?;
            blob_digests.insert(manifest.config_digest.clone());
            for layer in &manifest.layers {
                blob_digests.insert(layer.digest.clone());
            }
            let chain = parent_closure(root, &manifest.root_snapshot_id)?;
            for id in chain {
                snapshot_ids.insert(id.clone());
                let meta = load_snapshot(root, &id)?;
                blob_digests.insert(meta.digest);
            }
        }
    }

    let journal = root.join("lease.journal");
    if journal.is_file() {
        for line in std::fs::read_to_string(&journal)?.lines() {
            if line.trim().is_empty() {
                continue;
            }
            let v: serde_json::Value = serde_json::from_str(line)?;
            if v.get("op") == Some(&serde_json::Value::String("acquire".into())) {
                if let Some(d) = v.get("digest").and_then(|x| x.as_str()) {
                    if is_active_after_replay(root, &v)? {
                        blob_digests.insert(d.to_string());
                    }
                }
            }
        }
    }

    Ok((blob_digests, snapshot_ids))
}

fn is_active_after_replay(root: &Path, acquire: &serde_json::Value) -> Result<bool> {
    let lease_id = acquire["lease_id"].as_str().unwrap();
    let digest = acquire["digest"].as_str().unwrap();
    let mut active: HashMap<String, String> = HashMap::new();
    let journal = std::fs::read_to_string(root.join("lease.journal"))?;
    let mut start = 0usize;
    for (idx, line) in journal.lines().enumerate() {
        let v: serde_json::Value = serde_json::from_str(line)?;
        if v.get("op") == Some(&serde_json::Value::String("watermark".into())) {
            start = idx;
        }
    }
    for line in journal.lines().skip(start) {
        let v: serde_json::Value = serde_json::from_str(line)?;
        match v.get("op").and_then(|x| x.as_str()) {
            Some("acquire") => {
                active.insert(
                    v["lease_id"].as_str().unwrap().to_string(),
                    v["digest"].as_str().unwrap().to_string(),
                );
            }
            Some("release") => {
                active.remove(v["lease_id"].as_str().unwrap());
            }
            _ => {}
        }
    }
    Ok(active.get(lease_id) == Some(&digest.to_string()))
}

pub fn parent_closure(root: &Path, start: &str) -> Result<Vec<String>> {
    let mut chain = Vec::new();
    let mut current = Some(start.to_string());
    let mut seen = HashSet::new();
    while let Some(id) = current {
        if !seen.insert(id.clone()) {
            anyhow::bail!("cycle at {id}");
        }
        let meta = load_snapshot(root, &id)?;
        chain.push(id.clone());
        current = meta.parent;
    }
    Ok(chain)
}

pub fn load_snapshot(root: &Path, id: &str) -> Result<SnapshotMeta> {
    let path = root
        .join("snapshots")
        .join(id)
        .join(".rstore/snapshot.json");
    Ok(serde_json::from_slice(&std::fs::read(path)?)?)
}

pub fn inventory_blob_reachable(report: &serde_json::Value, digest: &str) -> bool {
    report["blobs"]
        .as_array()
        .unwrap_or(&Vec::new())
        .iter()
        .find(|b| b["digest"] == digest)
        .and_then(|b| b["reachable"].as_bool())
        .unwrap_or(false)
}
