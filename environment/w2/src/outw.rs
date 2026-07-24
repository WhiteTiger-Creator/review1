use serde_json::Value;
use std::fs;
use std::path::Path;

pub fn write_report(path: &Path, report: &Value) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let body = serde_json::to_string_pretty(report).unwrap() + "\n";
    fs::write(path, body)
}
