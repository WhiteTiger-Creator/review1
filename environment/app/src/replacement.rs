//! Preferred replacement wiring.
//! Automatic replacement resolution is intentionally incomplete.

#![allow(dead_code)]

use std::collections::HashMap;

/// Returns the configured preference map without validating or applying it.
pub fn preference_map_stub(prefs: &HashMap<String, String>) -> HashMap<String, String> {
    prefs.clone()
}
