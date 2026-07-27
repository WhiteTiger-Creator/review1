use thiserror::Error;

#[derive(Debug, Error)]
pub enum VaultError {
    #[error("database error: {0}")]
    Database(String),
    #[error("crypto error: {0}")]
    Crypto(String),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("invalid state: {0}")]
    InvalidState(String),
    #[error("incompatible schema: {0}")]
    Incompatible(String),
    #[error("io error: {0}")]
    Io(String),
    #[error("config error: {0}")]
    Config(String),
}

impl From<rusqlite::Error> for VaultError {
    fn from(value: rusqlite::Error) -> Self {
        Self::Database(value.to_string())
    }
}

impl From<std::io::Error> for VaultError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value.to_string())
    }
}

impl From<serde_json::Error> for VaultError {
    fn from(value: serde_json::Error) -> Self {
        Self::Config(value.to_string())
    }
}
