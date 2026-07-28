//! Hierarchical `.cargo/config.toml` discovery, fixture-local only.

use crate::error::AuditorError;
use crate::paths;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Discovered {
    pub absolute_path: PathBuf,
    /// 0 at the invocation directory, increasing toward the fixture root.
    pub discovery_depth: u32,
}

/// Walk from `invocation` up to and including `fixture_root`, recording every
/// `.cargo/config.toml` encountered. Never reads above the fixture root and
/// never consults `$CARGO_HOME`.
pub fn discover_configs(
    fixture_root: &Path,
    invocation: &Path,
) -> Result<Vec<Discovered>, AuditorError> {
    let root = paths::lexical_normalize(fixture_root);
    let mut current = paths::lexical_normalize(invocation);
    let mut depth = 0u32;
    let mut out = Vec::new();
    loop {
        let config = current.join(".cargo").join("config.toml");
        if config.is_file() {
            out.push(Discovered {
                absolute_path: config,
                discovery_depth: depth,
            });
        }
        if current == root {
            break;
        }
        match current.parent() {
            Some(parent) => {
                current = parent.to_path_buf();
                depth += 1;
            }
            None => break,
        }
    }
    Ok(out)
}
