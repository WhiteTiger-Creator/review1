//! Canonical JSON rendering and SHA-256 identities.

use crate::linalg::dense::format_f64;
use sha2::{Digest, Sha256};

pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    hex::encode(h.finalize())
}

pub fn render_f64(v: f64) -> String {
    format_f64(v)
}

pub fn indent_block(s: &str, spaces: usize) -> String {
    let pad = " ".repeat(spaces);
    s.lines()
        .map(|line| {
            if line.is_empty() {
                String::new()
            } else {
                format!("{pad}{line}")
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn json_string(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| format!("\"{s}\""))
}

pub fn join_canonical(parts: &[String]) -> String {
    let mut out = String::new();
    out.push_str("{\n");
    for (i, p) in parts.iter().enumerate() {
        out.push_str(p);
        if i + 1 != parts.len() {
            out.push(',');
        }
        out.push('\n');
    }
    out.push_str("}\n");
    out
}
