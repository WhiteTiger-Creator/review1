use std::fmt;

#[derive(Debug)]
pub struct FatalInputError {
    pub message: String,
}

impl FatalInputError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for FatalInputError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for FatalInputError {}

pub type Result<T> = std::result::Result<T, FatalInputError>;
