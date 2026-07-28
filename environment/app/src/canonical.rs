//! Canonical JSON serialization and SHA-256 digests.

use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub fn sort_unique_components(components: &[String]) -> Vec<String> {
    let mut values: Vec<String> = components.iter().cloned().collect();
    values.sort();
    values.dedup();
    values
}

pub fn sort_unique_strings(values: &[String]) -> Vec<String> {
    let mut out: Vec<String> = values.iter().cloned().collect();
    out.sort();
    out.dedup();
    out
}

pub fn normalize_name(name: &str) -> String {
    name.trim().to_ascii_lowercase()
}

fn sort_json_keys(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut btree: BTreeMap<String, Value> = BTreeMap::new();
            for (key, child) in map {
                btree.insert(key.clone(), sort_json_keys(child));
            }
            Value::Object(btree.into_iter().collect())
        }
        Value::Array(items) => Value::Array(items.iter().map(sort_json_keys).collect()),
        _ => value.clone(),
    }
}

pub fn compact_json(value: &Value) -> String {
    let sorted = sort_json_keys(value);
    serde_json::to_string(&sorted).expect("compact json serialization")
}

pub fn sha256_hex_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub fn sha256_hex_value(value: &Value) -> String {
    sha256_hex_bytes(compact_json(value).as_bytes())
}

pub fn sha256_hex_serializable<T: Serialize>(value: &T) -> Result<String, serde_json::Error> {
    let json = serde_json::to_value(value)?;
    Ok(sha256_hex_value(&json))
}

pub fn pretty_json<T: Serialize>(value: &T) -> Result<Vec<u8>, serde_json::Error> {
    let rendered = serde_json::to_string_pretty(value)?;
    let mut bytes = rendered.into_bytes();
    if !bytes.ends_with(b"\n") {
        bytes.push(b'\n');
    }
    Ok(bytes)
}
