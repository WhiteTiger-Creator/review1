use serde::{Deserialize, Serialize};
use sha2::{Digest as ShaDigest, Sha256};
use std::fmt;
use std::str::FromStr;
use thiserror::Error;

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Digest(String);

#[derive(Debug, Error)]
pub enum DigestError {
    #[error("invalid digest format: {0}")]
    Invalid(String),
}

impl Digest {
    pub fn from_bytes(bytes: &[u8]) -> Self {
        let hex = hex::encode(bytes);
        Self(format!("sha256:{hex}"))
    }

    pub fn from_hex(hex: &str) -> Result<Self, DigestError> {
        let clean = hex.strip_prefix("sha256:").unwrap_or(hex);
        if clean.len() != 64 || !clean.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err(DigestError::Invalid(hex.to_string()));
        }
        Ok(Self(format!("sha256:{clean}")))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn hex(&self) -> &str {
        self.0.strip_prefix("sha256:").unwrap_or(&self.0)
    }

    pub fn hash_bytes(data: &[u8]) -> Self {
        let mut hasher = Sha256::new();
        hasher.update(data);
        Self::from_bytes(&hasher.finalize())
    }
}

impl fmt::Display for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl FromStr for Digest {
    type Err = DigestError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Self::from_hex(s)
    }
}
