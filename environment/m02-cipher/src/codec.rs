use chacha20poly1305::aead::{Aead, KeyInit};
use chacha20poly1305::{ChaCha20Poly1305, Nonce};
use m01_seal::VaultError;

use crate::keys::derive_key;

pub fn encrypt_payload(key_id: &str, nonce_hex: &str, plaintext: &str) -> Result<Vec<u8>, VaultError> {
    let key = derive_key(key_id);
    let cipher = ChaCha20Poly1305::new(&key.into());
    let nonce_bytes = hex::decode(nonce_hex).map_err(|e| VaultError::Crypto(e.to_string()))?;
    if nonce_bytes.len() != 12 {
        return Err(VaultError::Crypto("nonce must be 12 bytes".into()));
    }
    let mut nonce_arr = [0u8; 12];
    nonce_arr.copy_from_slice(&nonce_bytes);
    let nonce = Nonce::from(nonce_arr);
    cipher
        .encrypt(&nonce, plaintext.as_bytes())
        .map_err(|e| VaultError::Crypto(e.to_string()))
}

pub fn decrypt_payload(key_id: &str, nonce_hex: &str, ciphertext: &[u8]) -> Result<String, VaultError> {
    let key = derive_key(key_id);
    let cipher = ChaCha20Poly1305::new(&key.into());
    let nonce_bytes = hex::decode(nonce_hex).map_err(|e| VaultError::Crypto(e.to_string()))?;
    if nonce_bytes.len() != 12 {
        return Err(VaultError::Crypto("nonce must be 12 bytes".into()));
    }
    let mut nonce_arr = [0u8; 12];
    nonce_arr.copy_from_slice(&nonce_bytes);
    let nonce = Nonce::from(nonce_arr);
    let plain = cipher
        .decrypt(&nonce, ciphertext)
        .map_err(|e| VaultError::Crypto(e.to_string()))?;
    String::from_utf8(plain).map_err(|e| VaultError::Crypto(e.to_string()))
}
