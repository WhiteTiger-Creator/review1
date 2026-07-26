//! Strict UTF-8 JSON decoding helpers.

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use serde::Deserialize;
use serde_json::{Map, Value};
use std::fs;
use std::path::Path;

pub fn read_bytes(path: &Path) -> AppResult<Vec<u8>> {
    fs::read(path).map_err(|e| {
        (
            FailureCode::EPath,
            format!("cannot read {}: {e}", path.display()),
        )
    })
}

pub fn parse_object(bytes: &[u8]) -> AppResult<Map<String, Value>> {
    parse_object_with_code(bytes, FailureCode::EModelSchema)
}

pub fn parse_object_with_code(bytes: &[u8], code: FailureCode) -> AppResult<Map<String, Value>> {
    let text = std::str::from_utf8(bytes).map_err(|_| (code, "malformed UTF-8".into()))?;
    // Reject duplicate keys via manual scan of object key occurrences at top and nested levels
    reject_duplicate_keys(text, code)?;
    let mut de = serde_json::Deserializer::from_str(text);
    let value = Value::deserialize(&mut de).map_err(|e| (code, format!("json parse: {e}")))?;
    de.end()
        .map_err(|e| (code, format!("trailing bytes: {e}")))?;
    match value {
        Value::Object(map) => Ok(map),
        _ => fail(code, "root must be object"),
    }
}

fn reject_duplicate_keys(text: &str, code: FailureCode) -> AppResult<()> {
    // Lightweight structural scan: track brace depth and keys at each object depth.
    let bytes = text.as_bytes();
    let mut i = 0usize;
    let mut stack: Vec<std::collections::HashSet<String>> = Vec::new();
    while i < bytes.len() {
        let c = bytes[i];
        if c == b'"' {
            i += 1;
            let start = i;
            while i < bytes.len() {
                if bytes[i] == b'\\' {
                    i += 2;
                    continue;
                }
                if bytes[i] == b'"' {
                    break;
                }
                i += 1;
            }
            let key = std::str::from_utf8(&bytes[start..i]).unwrap_or("");
            i += 1;
            // skip whitespace
            while i < bytes.len() && bytes[i].is_ascii_whitespace() {
                i += 1;
            }
            if i < bytes.len() && bytes[i] == b':' {
                if let Some(set) = stack.last_mut() {
                    if !set.insert(key.to_string()) {
                        return fail(code, format!("duplicate object member {key}"));
                    }
                }
            }
            continue;
        }
        match c {
            b'{' => stack.push(std::collections::HashSet::new()),
            b'}' => {
                stack.pop();
            }
            _ => {}
        }
        i += 1;
    }
    Ok(())
}

pub fn require_string(map: &Map<String, Value>, key: &str, code: FailureCode) -> AppResult<String> {
    match map.get(key) {
        Some(Value::String(s)) => Ok(s.clone()),
        Some(_) => fail(code, format!("{key} must be string")),
        None => fail(code, format!("missing {key}")),
    }
}

pub fn require_f64(map: &Map<String, Value>, key: &str, code: FailureCode) -> AppResult<f64> {
    match map.get(key) {
        Some(Value::Number(n)) => n
            .as_f64()
            .filter(|v| v.is_finite())
            .ok_or_else(|| (code, format!("{key} must be finite number"))),
        Some(_) => fail(code, format!("{key} must be number")),
        None => fail(code, format!("missing {key}")),
    }
}

pub fn require_usize(map: &Map<String, Value>, key: &str, code: FailureCode) -> AppResult<usize> {
    let v = require_f64(map, key, code)?;
    if v.fract() != 0.0 || v < 0.0 {
        return fail(code, format!("{key} must be non-negative integer"));
    }
    Ok(v as usize)
}

pub fn require_array<'a>(
    map: &'a Map<String, Value>,
    key: &str,
    code: FailureCode,
) -> AppResult<&'a Vec<Value>> {
    match map.get(key) {
        Some(Value::Array(a)) => Ok(a),
        Some(_) => fail(code, format!("{key} must be array")),
        None => fail(code, format!("missing {key}")),
    }
}

pub fn matrix_from_value(v: &Value, n: usize, code: FailureCode) -> AppResult<Vec<Vec<f64>>> {
    let rows = match v {
        Value::Array(a) => a,
        _ => return fail(code, "matrix must be array"),
    };
    if rows.len() != n {
        return fail(code, "matrix row count mismatch");
    }
    let mut out = Vec::with_capacity(n);
    for row in rows {
        let cols = match row {
            Value::Array(a) => a,
            _ => return fail(code, "matrix row must be array"),
        };
        if cols.len() != n {
            return fail(code, "matrix column count mismatch");
        }
        let mut r = Vec::with_capacity(n);
        for c in cols {
            match c {
                Value::Number(num) => {
                    let f = num
                        .as_f64()
                        .ok_or_else(|| (code, "non-finite matrix entry".into()))?;
                    if !f.is_finite() {
                        return fail(code, "non-finite matrix entry");
                    }
                    r.push(f);
                }
                _ => return fail(code, "matrix entry must be number"),
            }
        }
        out.push(r);
    }
    Ok(out)
}

pub fn validate_identifier(id: &str, code: FailureCode) -> AppResult<()> {
    let b = id.as_bytes();
    if b.is_empty() || b.len() > 48 {
        return fail(code, "identifier length out of range");
    }
    if !b[0].is_ascii_alphanumeric() {
        return fail(code, "identifier must begin with letter or digit");
    }
    for &c in b {
        if !(c.is_ascii_alphanumeric() || c == b'.' || c == b'_' || c == b'-') {
            return fail(code, "identifier has illegal character");
        }
    }
    Ok(())
}

pub fn reject_unknown(
    map: &Map<String, Value>,
    allowed: &[&str],
    code: FailureCode,
) -> AppResult<()> {
    for k in map.keys() {
        if !allowed.contains(&k.as_str()) {
            return fail(code, format!("unknown member {k}"));
        }
    }
    Ok(())
}
