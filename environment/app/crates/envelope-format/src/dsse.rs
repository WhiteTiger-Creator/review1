use anyhow::{anyhow, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::canonical;
use crate::payload;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct EnvelopeSignature {
    pub key_id: String,
    pub signature: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Envelope {
    pub schema_version: u64,
    pub payload_type: String,
    pub payload: String,
    pub signatures: Vec<EnvelopeSignature>,
}

#[derive(Clone, Debug)]
pub struct VerifiedPayload {
    pub payload_type: String,
    pub payload_bytes: Vec<u8>,
    pub payload: Value,
    pub key_ids: Vec<String>,
}

pub fn signing_message(payload_type: &str, payload_bytes: &[u8]) -> Vec<u8> {
    let mut message = Vec::new();
    message.extend_from_slice(b"DAC1\0envelope\0");
    message.extend_from_slice(&(payload_type.len() as u32).to_be_bytes());
    message.extend_from_slice(payload_type.as_bytes());
    message.extend_from_slice(&(payload_bytes.len() as u64).to_be_bytes());
    message.extend_from_slice(payload_bytes);
    message
}

pub fn verify_envelope(envelope: &Envelope, keyring: &[(String, [u8; 32])]) -> Result<VerifiedPayload> {
    let payload_bytes = STANDARD.decode(&envelope.payload)?;
    let payload = canonical::parse_strict(std::str::from_utf8(&payload_bytes)?)?;
    payload::validate_payload_type(&envelope.payload_type)?;
    let message = signing_message(&envelope.payload_type, &payload_bytes);
    if envelope.signatures.is_empty() {
        anyhow::bail!("missing signatures");
    }
    let mut key_ids = Vec::new();
    for signature in &envelope.signatures {
        let public = keyring
            .iter()
            .find(|(key_id, _)| key_id == &signature.key_id)
            .map(|(_, bytes)| *bytes)
            .ok_or_else(|| anyhow!("unknown key"))?;
        let verifying_key = VerifyingKey::from_bytes(&public)?;
        let sig_bytes = STANDARD.decode(&signature.signature)?;
        let sig = Signature::from_slice(&sig_bytes)?;
        verifying_key.verify(&message, &sig)?;
        key_ids.push(signature.key_id.clone());
    }
    Ok(VerifiedPayload {
        payload_type: envelope.payload_type.clone(),
        payload_bytes,
        payload,
        key_ids,
    })
}
