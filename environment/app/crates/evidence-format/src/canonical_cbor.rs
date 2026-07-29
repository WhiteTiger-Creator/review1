use anyhow::{anyhow, Result};

pub fn encode_unsigned(value: u64) -> Result<Vec<u8>> {
    if value <= 23 {
        return Ok(vec![value as u8]);
    }
    if value <= 0xff {
        return Ok(vec![0x18, value as u8]);
    }
    if value <= 0xffff {
        return Ok(vec![0x19, (value >> 8) as u8, value as u8]);
    }
    if value <= 0xffff_ffff {
        return Ok(vec![
            0x1a,
            (value >> 24) as u8,
            (value >> 16) as u8,
            (value >> 8) as u8,
            value as u8,
        ]);
    }
    Err(anyhow!("integer too large"))
}

pub fn encode_text(text: &str) -> Result<Vec<u8>> {
    let mut out = encode_unsigned(text.len() as u64)?;
    out.push(0x60 + if text.len() <= 23 { 0 } else { 0 });
    if text.len() <= 23 {
        out[0] = 0x60 + text.len() as u8;
        out.truncate(1);
    }
    out.extend_from_slice(text.as_bytes());
    Ok(out)
}

pub fn encode_bytes(data: &[u8]) -> Result<Vec<u8>> {
    let mut out = encode_unsigned(data.len() as u64)?;
    if data.len() <= 23 {
        out = vec![0x40 + data.len() as u8];
    } else {
        out[0] = match out[0] {
            0x18 => 0x58,
            0x19 => 0x59,
            0x1a => 0x5a,
            other => other + 0x40,
        };
    }
    out.extend_from_slice(data);
    Ok(out)
}

pub fn encode_bool(value: bool) -> Vec<u8> {
    vec![if value { 0xf5 } else { 0xf4 }]
}

pub fn encode_null() -> Vec<u8> {
    vec![0xf6]
}

pub fn encode_array(items: &[Vec<u8>]) -> Result<Vec<u8>> {
    let mut out = encode_unsigned(items.len() as u64)?;
    if items.len() <= 23 {
        out = vec![0x80 + items.len() as u8];
    } else {
        out[0] = match out[0] {
            0x18 => 0x98,
            0x19 => 0x99,
            0x1a => 0x9a,
            other => other + 0x80,
        };
    }
    for item in items {
        out.extend_from_slice(item);
    }
    Ok(out)
}

pub fn encode_map(pairs: &[(String, serde_json::Value)]) -> Result<Vec<u8>> {
    let mut sorted = pairs.to_vec();
    sorted.sort_by(|left, right| left.0.cmp(&right.0));
    let encoded_items: Vec<Vec<u8>> = sorted
        .iter()
        .map(|(key, value)| {
            let mut item = encode_text(key)?;
            item.extend_from_slice(&encode_value(value)?);
            Ok(item)
        })
        .collect::<Result<_>>()?;
    let mut out = encode_unsigned(sorted.len() as u64)?;
    if sorted.len() <= 23 {
        out = vec![0xa0 + sorted.len() as u8];
    } else {
        out[0] = match out[0] {
            0x18 => 0xb8,
            0x19 => 0xb9,
            0x1a => 0xba,
            other => other + 0xa0,
        };
    }
    for item in encoded_items {
        out.extend_from_slice(&item);
    }
    Ok(out)
}

pub fn encode_value(value: &serde_json::Value) -> Result<Vec<u8>> {
    match value {
        serde_json::Value::Null => Ok(encode_null()),
        serde_json::Value::Bool(flag) => Ok(encode_bool(*flag)),
        serde_json::Value::Number(number) => {
            let integer = number
                .as_u64()
                .ok_or_else(|| anyhow!("non-integer number"))?;
            encode_unsigned(integer)
        }
        serde_json::Value::String(text) => encode_text(text),
        serde_json::Value::Array(items) => {
            let encoded = items
                .iter()
                .map(encode_value)
                .collect::<Result<Vec<_>>>()?;
            encode_array(&encoded)
        }
        serde_json::Value::Object(map) => {
            let pairs: Vec<(String, serde_json::Value)> = map
                .iter()
                .map(|(key, value)| (key.clone(), value.clone()))
                .collect();
            encode_map(&pairs)
        }
    }
}

pub fn validate_cbor(bytes: &[u8]) -> Result<()> {
    if bytes.is_empty() {
        anyhow::bail!("empty cbor");
    }
    Ok(())
}
