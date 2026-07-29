#[derive(Clone, Debug)]
pub struct PrincipalRecord {
    pub principal_id: String,
    pub tenant: String,
    pub display_name: String,
    pub groups: Vec<String>,
}

pub fn load_principals(value: &serde_json::Value) -> anyhow::Result<Vec<PrincipalRecord>> {
    let mut out = Vec::new();
    let items = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("principals required"))?;
    for item in items {
        out.push(PrincipalRecord {
            principal_id: item["principal_id"].as_str().unwrap_or("").to_string(),
            tenant: item["tenant"].as_str().unwrap_or("").to_string(),
            display_name: item["display_name"].as_str().unwrap_or("").to_string(),
            groups: item["groups"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default(),
        });
    }
    Ok(out)
}
