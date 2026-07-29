use crate::error::AuditorError;
use serde::Deserialize;
use std::path::Path;

#[derive(Debug, Clone)]
pub struct LockedPackage {
    pub name: String,
    pub version: String,
    pub source: String,
    pub checksum: String,
}

#[derive(Debug, Deserialize)]
struct LockFile {
    package: Option<Vec<LockPackage>>,
}

#[derive(Debug, Deserialize)]
struct LockPackage {
    name: String,
    version: String,
    source: Option<String>,
    checksum: Option<String>,
}

pub fn parse_registry_packages(path: &Path) -> Result<Vec<LockedPackage>, AuditorError> {
    let text = std::fs::read_to_string(path).map_err(|e| AuditorError::Io(path.to_path_buf(), e))?;
    let lock: LockFile = toml::from_str(&text)
        .map_err(|e| AuditorError::Fatal(format!("Cargo.lock parse: {e}")))?;
    let mut out = Vec::new();
    for pkg in lock.package.unwrap_or_default() {
        if let (Some(source), Some(checksum)) = (pkg.source, pkg.checksum) {
            if source.starts_with("registry+") {
                out.push(LockedPackage {
                    name: pkg.name,
                    version: pkg.version,
                    source,
                    checksum,
                });
            }
        }
    }
    out.sort_by(|a, b| (&a.name, &a.version).cmp(&(&b.name, &b.version)));
    Ok(out)
}
