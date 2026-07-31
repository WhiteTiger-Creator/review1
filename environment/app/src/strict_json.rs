use anyhow::{bail, Result};
use serde::de::{self, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::Value;
use std::fmt;

use crate::models::ParsedClientData;

/// Narrow duplicate-key-aware object parser for clientDataJSON.
pub fn parse_client_data_object(bytes: &[u8]) -> Result<ParsedClientData> {
    let text = std::str::from_utf8(bytes).map_err(|_| anyhow::anyhow!("invalid utf-8"))?;
    let mut de = serde_json::Deserializer::from_str(text);
    let value = de::Deserialize::deserialize(&mut de).map_err(|e| anyhow::anyhow!("{e}"))?;
    de.end().map_err(|e| anyhow::anyhow!("invalid json: {e}"))?;
    let ValueRejectDupes(value) = value;
    let obj = match value {
        Value::Object(o) => o,
        _ => bail!("top-level must be object"),
    };

    let type_value = match obj.get("type") {
        Some(Value::String(s)) => s.clone(),
        Some(_) => bail!("type must be string"),
        None => bail!("missing type"),
    };
    let challenge = match obj.get("challenge") {
        Some(Value::String(s)) => s.clone(),
        Some(_) => bail!("challenge must be string"),
        None => bail!("missing challenge"),
    };
    let origin = match obj.get("origin") {
        Some(Value::String(s)) => s.clone(),
        Some(_) => bail!("origin must be string"),
        None => bail!("missing origin"),
    };
    let cross_origin = match obj.get("crossOrigin") {
        None => None,
        Some(Value::Bool(b)) => Some(*b),
        Some(_) => bail!("crossOrigin must be boolean"),
    };

    Ok(ParsedClientData {
        type_value,
        challenge,
        origin,
        cross_origin,
    })
}

struct ValueRejectDupes(Value);

impl<'de> de::Deserialize<'de> for ValueRejectDupes {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer
            .deserialize_any(ValueVisitor)
            .map(ValueRejectDupes)
    }
}

struct ValueVisitor;

impl<'de> Visitor<'de> for ValueVisitor {
    type Value = Value;

    fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
        write!(f, "a JSON value")
    }

    fn visit_bool<E: de::Error>(self, v: bool) -> Result<Self::Value, E> {
        Ok(Value::Bool(v))
    }
    fn visit_i64<E: de::Error>(self, v: i64) -> Result<Self::Value, E> {
        Ok(Value::Number(v.into()))
    }
    fn visit_u64<E: de::Error>(self, v: u64) -> Result<Self::Value, E> {
        Ok(Value::Number(v.into()))
    }
    fn visit_f64<E: de::Error>(self, v: f64) -> Result<Self::Value, E> {
        Ok(serde_json::Number::from_f64(v)
            .map(Value::Number)
            .unwrap_or(Value::Null))
    }
    fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
        Ok(Value::String(v.to_string()))
    }
    fn visit_string<E: de::Error>(self, v: String) -> Result<Self::Value, E> {
        Ok(Value::String(v))
    }
    fn visit_none<E: de::Error>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }
    fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
        Ok(Value::Null)
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
        let mut out = Vec::new();
        while let Some(ValueRejectDupes(v)) = seq.next_element()? {
            out.push(v);
        }
        Ok(Value::Array(out))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        let mut obj = serde_json::Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if obj.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate key: {key}")));
            }
            let ValueRejectDupes(value) = map.next_value()?;
            obj.insert(key, value);
        }
        Ok(Value::Object(obj))
    }
}
