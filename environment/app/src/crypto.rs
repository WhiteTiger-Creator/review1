use anyhow::{bail, Result};
use base64ct::{Base64UrlUnpadded, Encoding};
use p256::ecdsa::{signature::Verifier, Signature, VerifyingKey};
use p256::elliptic_curve::sec1::FromEncodedPoint;
use p256::{EncodedPoint, PublicKey};
use sha2::{Digest, Sha256};

pub fn sha256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hasher.finalize().into()
}

pub fn b64url_encode(data: &[u8]) -> String {
    Base64UrlUnpadded::encode_string(data)
}

pub fn verify_es256_der(
    public_key_sec1: &[u8],
    message: &[u8],
    signature_der: &[u8],
) -> Result<()> {
    if public_key_sec1.len() != 65 || public_key_sec1[0] != 0x04 {
        bail!("invalid public key");
    }
    let point = EncodedPoint::from_bytes(public_key_sec1)
        .map_err(|_| anyhow::anyhow!("invalid public key"))?;
    let public = PublicKey::from_encoded_point(&point);
    if bool::from(public.is_none()) {
        bail!("invalid public key");
    }
    let public = public.unwrap();
    let verifying_key = VerifyingKey::from(public);
    let signature =
        Signature::from_der(signature_der).map_err(|_| anyhow::anyhow!("malformed DER"))?;
    // Reject non-minimal encodings that from_der may accept inconsistently by
    // requiring round-trip equality to the stored DER bytes.
    let reencoded = signature.to_der();
    if reencoded.as_bytes() != signature_der {
        bail!("malformed DER");
    }
    verifying_key
        .verify(message, &signature)
        .map_err(|_| anyhow::anyhow!("verification failed"))?;
    Ok(())
}

pub fn signed_message(authenticator_data: &[u8], client_data_json: &[u8]) -> Vec<u8> {
    let digest_input = compact_json_bytes(client_data_json);
    let mut out = Vec::with_capacity(authenticator_data.len() + 32);
    out.extend_from_slice(authenticator_data);
    out.extend_from_slice(&sha256(&digest_input));
    out
}

fn compact_json_bytes(raw: &[u8]) -> Vec<u8> {
    if let Ok(v) = serde_json::from_slice::<serde_json::Value>(raw) {
        if let Ok(bytes) = serde_json::to_vec(&v) {
            return bytes;
        }
    }
    raw.to_vec()
}
