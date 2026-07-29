//! Core repair logic for `rotctl repair`.
//!
//! `main.rs` already owns argument parsing, batch framing, and stdin/stdout.
//! This module is the only piece left to implement. See
//! `/app/docs/rotation-contract.md` for the exact per-window input and
//! output shapes `main.rs` reads and writes.

/// Compute the minimum number of slot tags that must be corrected so that
/// this window's tag array becomes explainable by some legitimate rotate
/// history, and return one such corrected array.
///
/// `a` holds `n` recorded tags, each already validated to be in `[1, m]`.
/// The returned array must also hold values in `[1, m]`, must be one a
/// legitimate rotate history could actually produce (see the contract doc
/// for what that means), and must differ from `a` in exactly the returned
/// count of positions.
pub fn repair(n: usize, m: usize, a: &[u32]) -> (usize, Vec<u32>) {
    let _ = (n, m, a);
    unimplemented!("rotation repair logic not yet implemented")
}
