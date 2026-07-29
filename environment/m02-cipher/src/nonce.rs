use sha2::{Digest, Sha256};

pub fn allocate_nonce(
    key_id: &str,
    generation_id: i64,
    reservation_sequence: i64,
    slot: i64,
) -> String {
    let material = format!(
        "{key_id}:{generation_id}:{reservation_sequence}:{slot}:vault-nonce-v1"
    );
    let digest = Sha256::digest(material.as_bytes());
    hex::encode(&digest[..12])
}
