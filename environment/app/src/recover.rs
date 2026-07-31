//! Unlock-code recovery.
//!
//! Returns the key stream the given body accepts, or None when no stream can be
//! reconstructed for it.

pub fn recover(body: &[u8]) -> Option<Vec<u8>> {
    let _ = body;
    None
}
