use std::fmt;

#[derive(Debug, Clone)]
pub struct FatalError {
    pub token: &'static str,
    pub message: String,
}

impl FatalError {
    pub fn new(token: &'static str, message: impl Into<String>) -> Self {
        Self {
            token,
            message: message.into(),
        }
    }
}

impl fmt::Display for FatalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.token, self.message)
    }
}

impl std::error::Error for FatalError {}

pub const MISSING_REQUIRED_INPUT: &str = "missing_required_input";
pub const MALFORMED_JSON: &str = "malformed_json";
pub const INVALID_INPUT_SCHEMA: &str = "invalid_input_schema";
pub const DUPLICATE_DECLARATION_INDEX: &str = "duplicate_declaration_index";
pub const DUPLICATE_FIND_REQUEST_INDEX: &str = "duplicate_find_request_index";
pub const DUPLICATE_CONFIGURE_REQUEST_INDEX: &str = "duplicate_configure_request_index";
pub const UNKNOWN_REFERENCE: &str = "unknown_reference";
pub const INVALID_VERSION: &str = "invalid_version";
pub const CONFLICTING_DECLARATION_FLAGS: &str = "conflicting_declaration_flags";
pub const DUPLICATE_TARGET_PRODUCER: &str = "duplicate_target_producer";
pub const UNKNOWN_TARGET_REFERENCE: &str = "unknown_target_reference";
pub const TARGET_DEPENDENCY_CYCLE: &str = "target_dependency_cycle";
pub const OUTPUT_WRITE_FAILED: &str = "output_write_failed";
pub const NOT_IMPLEMENTED: &str = "not_implemented";
