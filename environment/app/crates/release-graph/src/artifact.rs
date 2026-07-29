#[derive(Clone, Debug)]
pub struct ArtifactRecord {
    pub digest: String,
    pub media_type: String,
    pub tenant: String,
    pub namespace: String,
    pub name: String,
    pub version: String,
}

pub fn load_artifacts(value: &serde_json::Value) -> anyhow::Result<Vec<ArtifactRecord>> {
    let mut out = Vec::new();
    let items = value["artifacts"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("artifacts required"))?;
    for item in items {
        out.push(ArtifactRecord {
            digest: item["digest"].as_str().unwrap_or("").to_string(),
            media_type: item["media_type"].as_str().unwrap_or("").to_string(),
            tenant: item["tenant"].as_str().unwrap_or("").to_string(),
            namespace: item["namespace"].as_str().unwrap_or("").to_string(),
            name: item["name"].as_str().unwrap_or("").to_string(),
            version: item["version"].as_str().unwrap_or("").to_string(),
        });
    }
    Ok(out)
}
