#[derive(Clone, Debug)]
pub struct ThresholdRule {
    pub threshold_id: String,
    pub predicate: String,
    pub minimum_principals: usize,
}

#[derive(Clone, Debug)]
pub struct RequirementRule {
    pub role: String,
    pub tenant: String,
    pub namespace_pattern: String,
    pub media_type: String,
    pub required_predicates: Vec<String>,
    pub threshold_rules: Vec<ThresholdRule>,
}

#[derive(Clone, Debug)]
pub struct PolicyDocument {
    pub requirements: Vec<RequirementRule>,
}

pub fn load_policy(value: &serde_json::Value) -> anyhow::Result<PolicyDocument> {
    let mut requirements = Vec::new();
    let items = value["requirements"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("requirements required"))?;
    for item in items {
        let selector = &item["selector"];
        let mut thresholds = Vec::new();
        if let Some(rules) = item["threshold_rules"].as_array() {
            for rule in rules {
                thresholds.push(ThresholdRule {
                    threshold_id: rule["threshold_id"].as_str().unwrap_or("").to_string(),
                    predicate: rule["predicate"].as_str().unwrap_or("").to_string(),
                    minimum_principals: rule["minimum_principals"].as_u64().unwrap_or(1) as usize,
                });
            }
        }
        requirements.push(RequirementRule {
            role: item["role"].as_str().unwrap_or("").to_string(),
            tenant: selector["tenant"].as_str().unwrap_or("*").to_string(),
            namespace_pattern: selector["namespace_pattern"].as_str().unwrap_or("**").to_string(),
            media_type: selector["media_type"].as_str().unwrap_or("*").to_string(),
            required_predicates: item["required_predicates"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default(),
            threshold_rules: thresholds,
        });
    }
    Ok(PolicyDocument { requirements })
}

pub fn select_requirement<'a>(
    policy: &'a PolicyDocument,
    tenant: &str,
    namespace: &str,
    media_type: &str,
) -> Option<&'a RequirementRule> {
    policy
        .requirements
        .iter()
        .find(|rule| {
            (rule.tenant == "*" || rule.tenant == tenant)
                && crate::scope::matches_namespace(&rule.namespace_pattern, namespace)
                && (rule.media_type == "*" || rule.media_type == media_type)
        })
}
