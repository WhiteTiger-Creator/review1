use crate::legacy::{legacy_allows_predicate, legacy_namespace_allowed, LegacyReceipt};

#[derive(Clone, Debug)]
pub struct LegacyProjection {
    pub artifact_digest: String,
    pub predicate: String,
    pub principal: String,
}

pub fn project_legacy_evidence(
    receipt: &LegacyReceipt,
    namespace: &str,
    namespace_scope: &str,
    principal: &str,
) -> anyhow::Result<LegacyProjection> {
    if !legacy_namespace_allowed(namespace, namespace_scope) {
        anyhow::bail!("legacy namespace out of scope");
    }
    if !legacy_allows_predicate("build") {
        anyhow::bail!("legacy predicate unsupported");
    }
    Ok(LegacyProjection {
        artifact_digest: receipt.artifact_digest.clone(),
        predicate: "build".to_string(),
        principal: principal.to_string(),
    })
}
