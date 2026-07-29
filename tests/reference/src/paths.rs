use crate::error::AuditorError;
use std::path::{Component, Path, PathBuf};

pub fn normalize_abs(path: &Path) -> Result<PathBuf, AuditorError> {
    let abs = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| AuditorError::Fatal(format!("cwd: {e}")))?
            .join(path)
    };
    Ok(lexical_normalize(&abs))
}

pub fn lexical_normalize(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for comp in path.components() {
        match comp {
            Component::Prefix(p) => out.push(p.as_os_str()),
            Component::RootDir => out.push("/"),
            Component::CurDir => {}
            Component::ParentDir => { out.pop(); }
            Component::Normal(c) => out.push(c),
        }
    }
    out
}

pub fn is_within(root: &Path, path: &Path) -> bool {
    let root = lexical_normalize(root);
    let path = lexical_normalize(path);
    path.starts_with(&root)
}

pub fn rel_to(root: &Path, path: &Path) -> String {
    let root = lexical_normalize(root);
    let path = lexical_normalize(path);
    path.strip_prefix(&root)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().replace('\\', "/"))
}

pub fn config_path_base(config_file: &Path) -> PathBuf {
    let parent = config_file.parent().unwrap_or(Path::new("."));
    parent.parent().unwrap_or(parent).to_path_buf()
}

pub fn sha256_file(path: &Path) -> Result<String, AuditorError> {
    let bytes = std::fs::read(path).map_err(|e| AuditorError::Io(path.to_path_buf(), e))?;
    Ok(sha256_bytes(&bytes))
}

pub fn sha256_bytes(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(bytes);
    hex::encode(h.finalize())
}

pub fn resolve_path_keys(
    fixture_root: &Path,
    invocation_dir: &Path,
    merged: &crate::coalesce::MergedConfig,
    request_id: &str,
) -> Result<Vec<crate::report::PathResolutionRow>, AuditorError> {
    use crate::coalesce::ConfigValue;
    use crate::report::PathResolutionRow;
    let mut rows = Vec::new();
    for (key, cell) in merged.values.iter() {
        let is_path_key = key.ends_with(".directory")
            || key.ends_with(".local-registry")
            || key == "build.target-dir";
        if !is_path_key { continue; }
        let ConfigValue::String(raw) = &cell.value else { continue; };
        let base = cell.path_base.clone().unwrap_or_else(|| invocation_dir.to_path_buf());
        let joined = if Path::new(raw).is_absolute() { PathBuf::from(raw) } else { base.join(raw) };
        let normalized = lexical_normalize(&joined);
        if !is_within(fixture_root, &normalized) {
            return Err(AuditorError::Request(crate::error::RequestFailure {
                request_id: request_id.to_string(),
                stage: "path".into(),
                reason: "path_escape".into(),
                path_or_source: Some(key.clone()),
                details: format!("path escapes fixture root: {}", normalized.display()),
            }));
        }
        rows.push(PathResolutionRow {
            request_id: request_id.to_string(),
            key: key.clone(),
            raw_path: raw.clone(),
            base_path: rel_to(fixture_root, &base),
            normalized_path: rel_to(fixture_root, &normalized),
            exists: normalized.exists(),
        });
    }
    rows.sort_by(|a, b| (&a.request_id, &a.key).cmp(&(&b.request_id, &b.key)));
    Ok(rows)
}
