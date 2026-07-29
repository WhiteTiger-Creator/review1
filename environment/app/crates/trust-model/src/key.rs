use std::collections::HashMap;

#[derive(Clone, Debug)]
pub struct KeyRecord {
    pub key_id: String,
    pub public_key: [u8; 32],
    pub principal: String,
    pub tenant: String,
    pub valid_from_epoch: u64,
    pub valid_through_epoch: Option<u64>,
}

pub fn load_keys(value: &serde_json::Value) -> anyhow::Result<Vec<KeyRecord>> {
    let mut out = Vec::new();
    let items = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("keyring required"))?;
    for item in items {
        let bytes = decode_base64(item["public_key"].as_str().unwrap_or(""))?;
        if bytes.len() != 32 {
            anyhow::bail!("invalid public key length");
        }
        let mut public_key = [0u8; 32];
        public_key.copy_from_slice(&bytes);
        out.push(KeyRecord {
            key_id: item["key_id"].as_str().unwrap_or("").to_string(),
            public_key,
            principal: item["principal"].as_str().unwrap_or("").to_string(),
            tenant: item["tenant"].as_str().unwrap_or("").to_string(),
            valid_from_epoch: item["valid_from_epoch"].as_u64().unwrap_or(0),
            valid_through_epoch: item["valid_through_epoch"].as_u64(),
        });
    }
    Ok(out)
}

pub fn active_at(record: &KeyRecord, epoch: u64) -> bool {
    if epoch < record.valid_from_epoch {
        return false;
    }
    if let Some(end) = record.valid_through_epoch {
        if epoch > end {
            return false;
        }
    }
    true
}

pub fn keyring_map(records: &[KeyRecord]) -> HashMap<String, [u8; 32]> {
    records
        .iter()
        .map(|record| (record.key_id.clone(), record.public_key))
        .collect()
}

pub fn principal_for_key<'a>(key_id: &str, records: &'a [KeyRecord]) -> Option<&'a str> {
    records
        .iter()
        .find(|record| record.key_id == key_id)
        .map(|record| record.principal.as_str())
}

fn decode_base64(input: &str) -> anyhow::Result<Vec<u8>> {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::new();
    let mut buffer = 0u32;
    let mut bits = 0u32;
    for ch in input.bytes() {
        if ch == b'=' {
            break;
        }
        let value = TABLE
            .iter()
            .position(|item| *item == ch)
            .ok_or_else(|| anyhow::anyhow!("invalid base64"))? as u32;
        buffer = (buffer << 6) | value;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buffer >> bits) as u8);
            buffer &= (1 << bits) - 1;
        }
    }
    Ok(out)
}
