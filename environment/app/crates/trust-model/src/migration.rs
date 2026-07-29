use std::collections::HashMap;

#[derive(Clone, Debug)]
pub struct MigrationRecord {
    pub migration_id: String,
    pub from_principal: String,
    pub to_principal: String,
    pub tenant: String,
    pub namespace_pattern: String,
    pub predicates: Vec<String>,
    pub valid_from_epoch: u64,
    pub valid_through_epoch: Option<u64>,
}

pub fn resolve_principal(
    principal: &str,
    _tenant: &str,
    _namespace: &str,
    _predicate: &str,
    _epoch: u64,
    migrations: &[MigrationRecord],
) -> String {
    let mut current = principal.to_string();
    for record in migrations {
        if record.from_principal == current {
            current = record.to_principal.clone();
        }
    }
    current
}

pub fn load_migrations(value: &serde_json::Value) -> anyhow::Result<Vec<MigrationRecord>> {
    let mut out = Vec::new();
    let items = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("migration list required"))?;
    for item in items {
        out.push(MigrationRecord {
            migration_id: item["migration_id"].as_str().unwrap_or("").to_string(),
            from_principal: item["from_principal"].as_str().unwrap_or("").to_string(),
            to_principal: item["to_principal"].as_str().unwrap_or("").to_string(),
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
            valid_from_epoch: item["valid_from_epoch"].as_u64().unwrap_or(0),
            valid_through_epoch: item["valid_through_epoch"].as_u64(),
        });
    }
    Ok(out)
}

pub fn alias_table(migrations: &[MigrationRecord]) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for record in migrations {
        map.insert(record.from_principal.clone(), record.to_principal.clone());
    }
    map
}
