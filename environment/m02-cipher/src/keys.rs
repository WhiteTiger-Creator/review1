use chacha20poly1305::Key;
use sha2::{Digest, Sha256};

pub fn derive_key(key_id: &str) -> Key {
    let digest = Sha256::digest(format!("vault-fixture-key:{key_id}").as_bytes());
    Key::from_slice(&digest).to_owned()
}
