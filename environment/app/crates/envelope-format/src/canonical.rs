use anyhow::{anyhow, Result};
use serde_json::Value;

pub fn canonicalize(value: &Value) -> Result<String> {
    serde_json::to_string(value).map_err(|err| anyhow!(err))
}

pub fn parse_strict(text: &str) -> Result<Value> {
    serde_json::from_str(text).map_err(|err| anyhow!(err))
}

pub fn canonical_bytes(value: &Value) -> Result<Vec<u8>> {
    Ok(canonicalize(value)?.into_bytes())
}
