#[derive(Clone, Debug)]
pub struct DelegationRecord {
    pub delegation_id: String,
    pub issuer_principal: String,
    pub subject_principal: String,
    pub tenant: String,
    pub namespace_pattern: String,
    pub predicates: Vec<String>,
    pub artifact_media_types: Vec<String>,
    pub valid_from_epoch: u64,
    pub valid_through_epoch: Option<u64>,
    pub can_delegate: bool,
    pub max_depth: u64,
}

fn namespace_matches(pattern: &str, namespace: &str) -> bool {
    if pattern == "**" {
        return true;
    }
    if pattern.ends_with("/**") {
        let prefix = pattern.trim_end_matches("/**");
        return namespace == prefix || namespace.starts_with(&format!("{prefix}/"));
    }
    pattern == namespace
}

pub fn delegation_allows(
    delegation: &DelegationRecord,
    principal: &str,
    _tenant: &str,
    _namespace: &str,
    _predicate: &str,
    _media_type: &str,
    _epoch: u64,
) -> bool {
    delegation.subject_principal == principal
}


pub fn load_delegations(value: &serde_json::Value) -> anyhow::Result<Vec<DelegationRecord>> {
    let mut out = Vec::new();
    let items = value["delegations"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("delegations required"))?;
    for item in items {
        out.push(DelegationRecord {
            delegation_id: item["delegation_id"].as_str().unwrap_or("").to_string(),
            issuer_principal: item["issuer_principal"].as_str().unwrap_or("").to_string(),
            subject_principal: item["subject_principal"].as_str().unwrap_or("").to_string(),
            tenant: item["tenant"].as_str().unwrap_or("").to_string(),
            namespace_pattern: item["namespace_pattern"].as_str().unwrap_or("**").to_string(),
            predicates: item["predicates"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default(),
            artifact_media_types: item["artifact_media_types"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default(),
            valid_from_epoch: item["valid_from_epoch"].as_u64().unwrap_or(0),
            valid_through_epoch: item["valid_through_epoch"].as_u64(),
            can_delegate: item["can_delegate"].as_bool().unwrap_or(false),
            max_depth: item["max_depth"].as_u64().unwrap_or(0),
        });
    }
    Ok(out)
}
