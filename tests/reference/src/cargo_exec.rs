use crate::error::{AuditorError, RequestFailure};
use crate::coalesce::{ConfigValue, MergedConfig};
use crate::paths;
use crate::report::BuildRow;
use crate::replace_graph::TerminalSource;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub fn run_locked_offline(
    request_id: &str,
    fixture_root: &Path,
    workspace_manifest_rel: &str,
    lock_rel: &str,
    terminals: &BTreeMap<String, TerminalSource>,
    merged: &MergedConfig,
) -> Result<BuildRow, AuditorError> {
    let ws_manifest = fixture_root.join(workspace_manifest_rel);
    let ws_dir = ws_manifest
        .parent()
        .ok_or_else(|| AuditorError::Fatal("workspace manifest parent missing".into()))?;
    let lock_src = fixture_root.join(lock_rel);
    let lock_before = fs::read(&lock_src).map_err(|e| AuditorError::Io(lock_src.clone(), e))?;

    // Hash terminal source trees before build
    let crates_io_term = merged
        .values
        .get("source.crates-io.replace-with")
        .and_then(|c| match &c.value {
            ConfigValue::String(s) => Some(s.clone()),
            _ => None,
        });
    // Resolve terminal via terminals map: prefer crates-io chain end present in terminals
    let terminal = resolve_crates_io_terminal(merged, terminals).ok_or_else(|| {
        AuditorError::Request(RequestFailure {
            request_id: request_id.into(),
            stage: "build".into(),
            reason: "missing_terminal_source".into(),
            path_or_source: crates_io_term,
            details: "cannot resolve crates-io terminal for build".into(),
        })
    })?;
    let source_root = fixture_root.join(&terminal.root_rel);
    let source_hash_before = hash_tree(&source_root)?;

    let tmp = std::env::temp_dir().join(format!(
        "cargo-audit-build-{}-{}",
        request_id,
        std::process::id()
    ));
    if tmp.exists() {
        fs::remove_dir_all(&tmp).map_err(|e| AuditorError::Io(tmp.clone(), e))?;
    }
    copy_dir(ws_dir, &tmp)?;

    // Flatten effective source config for Cargo
    let cargo_home = tmp.join(".cargo-home");
    let target_dir = tmp.join("target-oracle-build");
    fs::create_dir_all(tmp.join(".cargo")).map_err(|e| AuditorError::Io(tmp.clone(), e))?;
    let abs_source = paths::lexical_normalize(&source_root);
    let config = match terminal.kind.as_str() {
        "directory" => format!(
            "[source.crates-io]\nreplace-with = \"terminal\"\n\n[source.terminal]\ndirectory = \"{}\"\n",
            abs_source.display()
        ),
        "local-registry" => format!(
            "[source.crates-io]\nreplace-with = \"terminal\"\n\n[source.terminal]\nlocal-registry = \"{}\"\n",
            abs_source.display()
        ),
        other => {
            return Err(AuditorError::Fatal(format!("bad terminal kind {other}")));
        }
    };
    fs::write(tmp.join(".cargo/config.toml"), config)
        .map_err(|e| AuditorError::Io(tmp.join(".cargo/config.toml"), e))?;

    let status = Command::new("cargo")
        .arg("build")
        .arg("--release")
        .arg("--locked")
        .arg("--offline")
        .arg("--manifest-path")
        .arg(tmp.join("Cargo.toml"))
        .arg("-p")
        .arg("cli")
        .current_dir(&tmp)
        .env("CARGO_HOME", &cargo_home)
        .env("CARGO_TARGET_DIR", &target_dir)
        .env("CARGO_NET_OFFLINE", "true")
        // Prevent parent-directory / user config leakage into the verification build.
        .env_remove("CARGO_CONFIG")
        .env("CARGO", "cargo")
        .output()
        .map_err(|e| AuditorError::Fatal(format!("failed to spawn cargo: {e}")))?;

    let exit_code = status.status.code().unwrap_or(101);
    let lock_after = fs::read(tmp.join("Cargo.lock")).unwrap_or_default();
    let lock_unchanged = lock_after == lock_before;
    let source_hash_after = hash_tree(&source_root)?;
    let source_bytes_unchanged = source_hash_after == source_hash_before;
    // Public contract: successful builds report artifact_count = 1 for the final cli executable only.
    let release_dir = target_dir.join("release");
    let has_cli = release_dir.join("cli").is_file() || release_dir.join("cli.exe").is_file();
    let artifact_count = if has_cli { 1 } else { 0 };

    let ok = status.status.success() && lock_unchanged && source_bytes_unchanged && has_cli;
    let row = BuildRow {
        request_id: request_id.to_string(),
        status: if ok { "success".into() } else { "failed".into() },
        exit_code,
        lock_unchanged,
        source_bytes_unchanged,
        artifact_count,
    };

    let _ = fs::remove_dir_all(&tmp);

    if !ok {
        let stderr = String::from_utf8_lossy(&status.stderr);
        return Err(AuditorError::Request(RequestFailure {
            request_id: request_id.into(),
            stage: "build".into(),
            reason: "locked_offline_build_failed".into(),
            path_or_source: Some(terminal.name.clone()),
            details: format!(
                "exit={exit_code} lock_unchanged={lock_unchanged} source_unchanged={source_bytes_unchanged} artifacts={artifact_count}; {}",
                stderr.chars().take(400).collect::<String>()
            ),
        }));
    }
    Ok(row)
}

fn resolve_crates_io_terminal(
    merged: &MergedConfig,
    terminals: &BTreeMap<String, TerminalSource>,
) -> Option<TerminalSource> {
    let mut cur = "crates-io".to_string();
    let mut guard = 0;
    while guard < 16 {
        guard += 1;
        if let Some(t) = terminals.get(&cur) {
            return Some(t.clone());
        }
        let key = format!("source.{cur}.replace-with");
        match merged.values.get(&key).map(|c| &c.value) {
            Some(ConfigValue::String(next)) => cur = next.clone(),
            _ => return terminals.values().next().cloned(),
        }
    }
    None
}

fn copy_dir(src: &Path, dst: &Path) -> Result<(), AuditorError> {
    fs::create_dir_all(dst).map_err(|e| AuditorError::Io(dst.to_path_buf(), e))?;
    for entry in fs::read_dir(src).map_err(|e| AuditorError::Io(src.to_path_buf(), e))? {
        let entry = entry.map_err(|e| AuditorError::Io(src.to_path_buf(), e))?;
        let path = entry.path();
        let name = entry.file_name();
        if name == "target" || name == "target-audit" || name == "target-oracle-build" {
            continue;
        }
        let to = dst.join(name);
        let meta = fs::symlink_metadata(&path).map_err(|e| AuditorError::Io(path.clone(), e))?;
        if meta.file_type().is_dir() && !meta.file_type().is_symlink() {
            copy_dir(&path, &to)?;
        } else if meta.file_type().is_symlink() {
            let target = fs::read_link(&path).map_err(|e| AuditorError::Io(path.clone(), e))?;
            #[cfg(unix)]
            std::os::unix::fs::symlink(&target, &to)
                .map_err(|e| AuditorError::Io(to.clone(), e))?;
        } else {
            fs::copy(&path, &to).map_err(|e| AuditorError::Io(to.clone(), e))?;
        }
    }
    Ok(())
}

fn hash_tree(root: &Path) -> Result<String, AuditorError> {
    let mut files = Vec::new();
    fn rec(dir: &Path, files: &mut Vec<PathBuf>) -> Result<(), AuditorError> {
        if !dir.exists() {
            return Ok(());
        }
        for entry in fs::read_dir(dir).map_err(|e| AuditorError::Io(dir.to_path_buf(), e))? {
            let entry = entry.map_err(|e| AuditorError::Io(dir.to_path_buf(), e))?;
            let path = entry.path();
            let meta = fs::symlink_metadata(&path).map_err(|e| AuditorError::Io(path.clone(), e))?;
            if meta.file_type().is_dir() && !meta.file_type().is_symlink() {
                rec(&path, files)?;
            } else if meta.file_type().is_file() {
                files.push(path);
            }
        }
        Ok(())
    }
    rec(root, &mut files)?;
    files.sort();
    let mut cat = Vec::new();
    for f in files {
        cat.extend(f.to_string_lossy().as_bytes());
        cat.push(0);
        cat.extend(fs::read(&f).map_err(|e| AuditorError::Io(f.clone(), e))?);
    }
    Ok(paths::sha256_bytes(&cat))
}

