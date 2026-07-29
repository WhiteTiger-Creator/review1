use std::fmt;
use std::io;
use std::path::PathBuf;

#[derive(Debug)]
pub struct RequestFailure {
    pub request_id: String,
    pub stage: String,
    pub reason: String,
    pub path_or_source: Option<String>,
    pub details: String,
}

#[derive(Debug)]
pub enum AuditorError {
    Fatal(String),
    Request(RequestFailure),
    Io(PathBuf, io::Error),
}

impl fmt::Display for AuditorError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AuditorError::Fatal(s) => write!(f, "{s}"),
            AuditorError::Request(r) => write!(
                f,
                "request {} stage={} reason={}: {}",
                r.request_id, r.stage, r.reason, r.details
            ),
            AuditorError::Io(p, e) => write!(f, "io {}: {e}", p.display()),
        }
    }
}

impl std::error::Error for AuditorError {}
