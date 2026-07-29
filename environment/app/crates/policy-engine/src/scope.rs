pub fn matches_namespace(pattern: &str, namespace: &str) -> bool {
    if pattern == "**" {
        return true;
    }
    if pattern.ends_with("/**") {
        let prefix = pattern.trim_end_matches("/**");
        return namespace == prefix || namespace.starts_with(&format!("{prefix}/"));
    }
    pattern == namespace
}

pub fn scope_allows(
    tenant: &str,
    namespace: &str,
    predicate: &str,
    rule_tenant: &str,
    rule_namespace: &str,
    required_predicates: &[String],
) -> bool {
    if rule_tenant != "*" && rule_tenant != tenant {
        return false;
    }
    if !matches_namespace(rule_namespace, namespace) {
        return false;
    }
    required_predicates.iter().any(|item| item == predicate)
}
