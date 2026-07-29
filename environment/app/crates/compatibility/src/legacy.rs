use base64::{engine::general_purpose::STANDARD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};

#[derive(Clone, Debug)]
pub struct LegacyReceipt {
    pub artifact_digest: String,
    pub builder_key_id: String,
    pub build_epoch: u64,
    pub source_digest: String,
    pub signature: String,
}

pub fn verify_legacy_receipt(
    receipt: &LegacyReceipt,
    public_key: &[u8; 32],
    body_without_signature: &[u8],
) -> anyhow::Result<()> {
    let mut message = Vec::new();
    message.extend_from_slice(b"DAC0\0legacy-build\0");
    message.extend_from_slice(body_without_signature);
    let key = VerifyingKey::from_bytes(public_key)?;
    let sig_bytes = STANDARD.decode(&receipt.signature)?;
    let signature = Signature::from_slice(&sig_bytes)?;
    key.verify(&message, &signature)?;
    Ok(())
}

pub fn legacy_allows_predicate(predicate: &str) -> bool {
    matches!(predicate, "build" | "test" | "package" | "release-approval")
}


pub fn legacy_namespace_allowed(namespace: &str, scope: &str) -> bool {
    namespace == scope || namespace.starts_with(&format!("{scope}/"))
}

pub fn load_legacy_receipt(value: &serde_json::Value) -> anyhow::Result<LegacyReceipt> {
    Ok(LegacyReceipt {
        artifact_digest: value["artifact_digest"].as_str().unwrap_or("").to_string(),
        builder_key_id: value["builder_key_id"].as_str().unwrap_or("").to_string(),
        build_epoch: value["build_epoch"].as_u64().unwrap_or(0),
        source_digest: value["source_digest"].as_str().unwrap_or("").to_string(),
        signature: value["signature"].as_str().unwrap_or("").to_string(),
    })
}
