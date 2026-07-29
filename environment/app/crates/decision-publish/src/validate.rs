use evidence_format::decision::{canonical_decision_bytes, DecisionDocument};
use evidence_format::canonical_cbor::validate_cbor;
use sha2::{Digest, Sha256};

pub fn decision_digest(bytes: &[u8]) -> String {
    format!("sha256:{}", hex::encode(Sha256::digest(bytes)))
}

pub fn generation_id(decision: &DecisionDocument, evidence: &[u8]) -> String {
    let decision_bytes = canonical_decision_bytes(decision).unwrap_or_default();
    let material = [decision_bytes.as_slice(), evidence].concat();
    format!("sha256:{}", hex::encode(Sha256::digest(material)))
}

pub fn validate_outputs(decision: &DecisionDocument, evidence: &[u8]) -> anyhow::Result<()> {
    validate_cbor(evidence)?;
    if decision.evidence_digest != format!("sha256:{}", hex::encode(Sha256::digest(evidence))) {
        anyhow::bail!("evidence digest mismatch");
    }
    if decision.decision != "approve" && decision.decision != "reject" {
        anyhow::bail!("invalid decision");
    }
    Ok(())
}
