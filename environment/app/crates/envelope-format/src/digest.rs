use sha2::{Digest, Sha256};

pub fn parse_digest(value: &str) -> anyhow::Result<[u8; 32]> {
    let prefix = "sha256:";
    let rest = value
        .strip_prefix(prefix)
        .ok_or_else(|| anyhow::anyhow!("invalid digest prefix"))?;
    let bytes = hex::decode(rest)?;
    if bytes.len() != 32 {
        anyhow::bail!("digest length mismatch");
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&bytes);
    Ok(out)
}

pub fn digest_bytes(data: &[u8]) -> String {
    format!("sha256:{}", hex::encode(Sha256::digest(data)))
}

pub fn envelope_digest(canonical_bytes: &[u8]) -> String {
    digest_bytes(canonical_bytes)
}

pub fn payload_digest(payload_bytes: &[u8]) -> String {
    digest_bytes(payload_bytes)
}

pub fn artifact_digest(content: &[u8]) -> String {
    digest_bytes(content)
}

pub fn subject_matches_artifact(subject: &str, artifact_digest: &str, envelope_digest: &str, payload_digest: &str) -> bool {
    subject == artifact_digest || subject == envelope_digest || subject == payload_digest
}


pub fn validate_subject_binding(
    subject: &str,
    artifact_digest: &str,
    envelope_digest: &str,
    payload_digest: &str,
) -> anyhow::Result<()> {
    if subject_matches_artifact(subject, artifact_digest, envelope_digest, payload_digest) {
        Ok(())
    } else {
        anyhow::bail!("subject digest binding mismatch")
    }
}
