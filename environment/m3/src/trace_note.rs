use std::fs::OpenOptions;
use std::io::Write;

/// Optional diagnostic note writer for operator sidecars.
pub fn append_note(path: &str, msg: &str) {
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{msg}");
    }
}
