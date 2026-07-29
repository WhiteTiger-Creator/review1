use crate::error::{AuditorError, RequestFailure};
use crate::input::SourceProfiles;
use crate::lock_sync::LockedPackage;
use crate::paths;
use crate::report::{IntegrityRow, LockReconciliationRow, PackageSourceRow, SourceRow};
use crate::replace_graph::TerminalSource;
use flate2::read::GzDecoder;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use tar::Archive;

pub fn reconcile_and_verify(
    request_id: &str,
    fixture_root: &Path,
    packages: &[LockedPackage],
    terminals: &BTreeMap<String, TerminalSource>,
    source_rows: &[SourceRow],
    _source_profiles: &SourceProfiles,
) -> Result<
    (
        Vec<PackageSourceRow>,
        Vec<LockReconciliationRow>,
        Vec<IntegrityRow>,
        Option<RequestFailure>,
    ),
    AuditorError,
> {
    let crates_io_terminal = source_rows
        .iter()
        .find(|s| s.source_name == "crates-io")
        .map(|s| s.terminal_source.clone())
        .ok_or_else(|| {
            AuditorError::Request(RequestFailure {
                request_id: request_id.into(),
                stage: "source".into(),
                reason: "missing_replacement_target".into(),
                path_or_source: Some("crates-io".into()),
                details: "crates-io source not configured".into(),
            })
        })?;

    let terminal = terminals.get(&crates_io_terminal).ok_or_else(|| {
        AuditorError::Request(RequestFailure {
            request_id: request_id.into(),
            stage: "source".into(),
            reason: "missing_replacement_target".into(),
            path_or_source: Some(crates_io_terminal.clone()),
            details: "terminal source missing".into(),
        })
    })?;

    let mut pkg_rows = Vec::new();
    let mut lock_rows = Vec::new();
    let mut integ_rows = Vec::new();
    let mut failure: Option<RequestFailure> = None;

    for pkg in packages {
        let rel_pkg = match terminal.kind.as_str() {
            "directory" => format!("{}/{}-{}", terminal.root_rel, pkg.name, pkg.version),
            "local-registry" => format!("{}/{}-{}.crate", terminal.root_rel, pkg.name, pkg.version),
            other => {
                return Err(AuditorError::Fatal(format!("unknown terminal kind {other}")));
            }
        };
        pkg_rows.push(PackageSourceRow {
            request_id: request_id.to_string(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            original_source: pkg.source.clone(),
            terminal_source: terminal.name.clone(),
            relative_package_path: rel_pkg.clone(),
        });

        let abs_root = fixture_root.join(&terminal.root_rel);
        let (status, checksum, integ) = match terminal.kind.as_str() {
            "directory" => verify_directory(
                request_id,
                &terminal.name,
                fixture_root,
                &abs_root,
                pkg,
            )?,
            "local-registry" => verify_local_registry(
                request_id,
                &terminal.name,
                fixture_root,
                &abs_root,
                pkg,
            )?,
            _ => unreachable!(),
        };
        integ_rows.extend(integ);
        lock_rows.push(LockReconciliationRow {
            request_id: request_id.to_string(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            lock_source: pkg.source.clone(),
            effective_source: format!("{}:{}", terminal.kind, terminal.root_rel),
            checksum: checksum.clone(),
            status: status.clone(),
        });
        if status != "matched" && failure.is_none() {
            failure = Some(RequestFailure {
                request_id: request_id.into(),
                stage: "lock".into(),
                reason: status,
                path_or_source: Some(format!("{}@{}", pkg.name, pkg.version)),
                details: "lock reconciliation failed".into(),
            });
        }
    }

    Ok((pkg_rows, lock_rows, integ_rows, failure))
}

fn verify_directory(
    request_id: &str,
    source_name: &str,
    fixture_root: &Path,
    root: &Path,
    pkg: &LockedPackage,
) -> Result<(String, String, Vec<IntegrityRow>), AuditorError> {
    let mut rows = Vec::new();
    let pkg_dir = root.join(format!("{}-{}", pkg.name, pkg.version));
    if !pkg_dir.is_dir() {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "directory_identity".into(),
            status: "package_missing".into(),
            details: paths::rel_to(fixture_root, &pkg_dir),
        });
        return Ok(("package_missing".into(), String::new(), rows));
    }

    // Reject unsafe symlinks
    for entry in walk_files(&pkg_dir)? {
        let meta = fs::symlink_metadata(&entry)
            .map_err(|e| AuditorError::Io(entry.clone(), e))?;
        if meta.file_type().is_symlink() {
            let target = fs::read_link(&entry).map_err(|e| AuditorError::Io(entry.clone(), e))?;
            let resolved = if target.is_absolute() {
                target
            } else {
                entry.parent().unwrap_or(Path::new(".")).join(target)
            };
            let resolved = paths::lexical_normalize(&resolved);
            if !paths::is_within(&pkg_dir, &resolved) {
                rows.push(IntegrityRow {
                    request_id: request_id.into(),
                    source_name: source_name.into(),
                    package_name: pkg.name.clone(),
                    version: pkg.version.clone(),
                    integrity_kind: "directory_symlink".into(),
                    status: "unsafe_symlink".into(),
                    details: paths::rel_to(fixture_root, &entry),
                });
                return Ok(("source_mismatch".into(), String::new(), rows));
            }
        }
    }

    let manifest = pkg_dir.join("Cargo.toml");
    let man_text = fs::read_to_string(&manifest).map_err(|e| AuditorError::Io(manifest.clone(), e))?;
    let man: toml::Value = toml::from_str(&man_text)
        .map_err(|e| AuditorError::Fatal(format!("manifest parse: {e}")))?;
    let m_name = man
        .get("package")
        .and_then(|p| p.get("name"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let m_ver = man
        .get("package")
        .and_then(|p| p.get("version"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if m_name != pkg.name || m_ver != pkg.version {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "directory_identity".into(),
            status: "identity_mismatch".into(),
            details: format!("{m_name}@{m_ver}"),
        });
        return Ok(("source_mismatch".into(), String::new(), rows));
    }
    rows.push(IntegrityRow {
        request_id: request_id.into(),
        source_name: source_name.into(),
        package_name: pkg.name.clone(),
        version: pkg.version.clone(),
        integrity_kind: "directory_identity".into(),
        status: "ok".into(),
        details: "manifest matches".into(),
    });

    let checksum_path = pkg_dir.join(".cargo-checksum.json");
    #[derive(Deserialize)]
    struct ChecksumFile {
        files: BTreeMap<String, String>,
        package: Option<String>,
    }
    let raw = fs::read_to_string(&checksum_path)
        .map_err(|e| AuditorError::Io(checksum_path.clone(), e))?;
    let ck: ChecksumFile = serde_json::from_str(&raw)
        .map_err(|e| AuditorError::Fatal(format!("checksum json: {e}")))?;
    let package_ck = ck.package.clone().unwrap_or_default();
    if package_ck != pkg.checksum {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "directory_checksum".into(),
            status: "checksum_mismatch".into(),
            details: format!("package field {package_ck} != lock {}", pkg.checksum),
        });
        return Ok(("checksum_mismatch".into(), package_ck, rows));
    }
    rows.push(IntegrityRow {
        request_id: request_id.into(),
        source_name: source_name.into(),
        package_name: pkg.name.clone(),
        version: pkg.version.clone(),
        integrity_kind: "directory_checksum".into(),
        status: "ok".into(),
        details: package_ck.clone(),
    });

    let mut listed: BTreeSet<String> = ck.files.keys().cloned().collect();
    for (rel, expect) in &ck.files {
        let file_path = pkg_dir.join(rel);
        if !file_path.is_file() {
            rows.push(IntegrityRow {
                request_id: request_id.into(),
                source_name: source_name.into(),
                package_name: pkg.name.clone(),
                version: pkg.version.clone(),
                integrity_kind: "directory_file".into(),
                status: "missing_file".into(),
                details: rel.clone(),
            });
            return Ok(("checksum_mismatch".into(), package_ck, rows));
        }
        let actual = paths::sha256_file(&file_path)?;
        if actual != *expect {
            rows.push(IntegrityRow {
                request_id: request_id.into(),
                source_name: source_name.into(),
                package_name: pkg.name.clone(),
                version: pkg.version.clone(),
                integrity_kind: "directory_file".into(),
                status: "checksum_mismatch".into(),
                details: rel.clone(),
            });
            return Ok(("checksum_mismatch".into(), package_ck, rows));
        }
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "directory_file".into(),
            status: "ok".into(),
            details: rel.clone(),
        });
    }

    // unexpected files
    for file in walk_files(&pkg_dir)? {
        let rel = file
            .strip_prefix(&pkg_dir)
            .unwrap()
            .to_string_lossy()
            .replace('\\', "/");
        if rel == ".cargo-checksum.json" {
            continue;
        }
        if !listed.contains(&rel) {
            rows.push(IntegrityRow {
                request_id: request_id.into(),
                source_name: source_name.into(),
                package_name: pkg.name.clone(),
                version: pkg.version.clone(),
                integrity_kind: "directory_unexpected_file".into(),
                status: "unexpected_file".into(),
                details: rel,
            });
            return Ok(("source_mismatch".into(), package_ck, rows));
        }
        listed.remove(&rel);
    }

    Ok(("matched".into(), package_ck, rows))
}

fn verify_local_registry(
    request_id: &str,
    source_name: &str,
    fixture_root: &Path,
    root: &Path,
    pkg: &LockedPackage,
) -> Result<(String, String, Vec<IntegrityRow>), AuditorError> {
    let mut rows = Vec::new();
    let index_file = root.join("index").join(index_rel(&pkg.name));
    if !index_file.is_file() {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "local_registry_index".into(),
            status: "package_missing".into(),
            details: paths::rel_to(fixture_root, &index_file),
        });
        return Ok(("package_missing".into(), String::new(), rows));
    }
    let text = fs::read_to_string(&index_file).map_err(|e| AuditorError::Io(index_file.clone(), e))?;
    let mut cksum = None;
    for line in text.lines() {
        let v: serde_json::Value = serde_json::from_str(line)
            .map_err(|e| AuditorError::Fatal(format!("index json: {e}")))?;
        if v.get("vers").and_then(|x| x.as_str()) == Some(pkg.version.as_str()) {
            cksum = v
                .get("cksum")
                .and_then(|x| x.as_str())
                .map(|s| s.to_string());
            break;
        }
    }
    let Some(cksum) = cksum else {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "local_registry_index".into(),
            status: "package_missing".into(),
            details: "version not in index".into(),
        });
        return Ok(("package_missing".into(), String::new(), rows));
    };
    rows.push(IntegrityRow {
        request_id: request_id.into(),
        source_name: source_name.into(),
        package_name: pkg.name.clone(),
        version: pkg.version.clone(),
        integrity_kind: "local_registry_index".into(),
        status: "ok".into(),
        details: cksum.clone(),
    });

    let archive = root.join(format!("{}-{}.crate", pkg.name, pkg.version));
    if !archive.is_file() {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "local_registry_archive".into(),
            status: "package_missing".into(),
            details: paths::rel_to(fixture_root, &archive),
        });
        return Ok(("package_missing".into(), cksum, rows));
    }
    let actual = paths::sha256_file(&archive)?;
    if actual != cksum || actual != pkg.checksum {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "local_registry_archive".into(),
            status: "checksum_mismatch".into(),
            details: format!("archive={actual} index={cksum} lock={}", pkg.checksum),
        });
        return Ok(("checksum_mismatch".into(), actual, rows));
    }
    rows.push(IntegrityRow {
        request_id: request_id.into(),
        source_name: source_name.into(),
        package_name: pkg.name.clone(),
        version: pkg.version.clone(),
        integrity_kind: "local_registry_archive".into(),
        status: "ok".into(),
        details: actual.clone(),
    });

    // Inspect archive paths + manifest
    let file = fs::File::open(&archive).map_err(|e| AuditorError::Io(archive.clone(), e))?;
    let dec = GzDecoder::new(file);
    let mut archive_tar = Archive::new(dec);
    let mut manifest = None;
    for entry in archive_tar
        .entries()
        .map_err(|e| AuditorError::Fatal(format!("tar: {e}")))?
    {
        let mut entry = entry.map_err(|e| AuditorError::Fatal(format!("tar entry: {e}")))?;
        let path = entry
            .path()
            .map_err(|e| AuditorError::Fatal(format!("tar path: {e}")))?
            .to_path_buf();
        let path_str = path.to_string_lossy();
        if path_str.contains("..") {
            rows.push(IntegrityRow {
                request_id: request_id.into(),
                source_name: source_name.into(),
                package_name: pkg.name.clone(),
                version: pkg.version.clone(),
                integrity_kind: "local_registry_path".into(),
                status: "unsafe_path".into(),
                details: path_str.into(),
            });
            return Ok(("source_mismatch".into(), actual, rows));
        }
        if path_str.ends_with("Cargo.toml") {
            let mut buf = String::new();
            entry
                .read_to_string(&mut buf)
                .map_err(|e| AuditorError::Fatal(format!("read manifest: {e}")))?;
            manifest = Some(buf);
        }
    }
    let Some(man_text) = manifest else {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "local_registry_identity".into(),
            status: "identity_mismatch".into(),
            details: "Cargo.toml missing in archive".into(),
        });
        return Ok(("source_mismatch".into(), actual, rows));
    };
    let man: toml::Value = toml::from_str(&man_text)
        .map_err(|e| AuditorError::Fatal(format!("manifest parse: {e}")))?;
    let m_name = man
        .get("package")
        .and_then(|p| p.get("name"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let m_ver = man
        .get("package")
        .and_then(|p| p.get("version"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if m_name != pkg.name || m_ver != pkg.version {
        rows.push(IntegrityRow {
            request_id: request_id.into(),
            source_name: source_name.into(),
            package_name: pkg.name.clone(),
            version: pkg.version.clone(),
            integrity_kind: "local_registry_identity".into(),
            status: "identity_mismatch".into(),
            details: format!("{m_name}@{m_ver}"),
        });
        return Ok(("source_mismatch".into(), actual, rows));
    }
    rows.push(IntegrityRow {
        request_id: request_id.into(),
        source_name: source_name.into(),
        package_name: pkg.name.clone(),
        version: pkg.version.clone(),
        integrity_kind: "local_registry_identity".into(),
        status: "ok".into(),
        details: "manifest matches".into(),
    });
    rows.push(IntegrityRow {
        request_id: request_id.into(),
        source_name: source_name.into(),
        package_name: pkg.name.clone(),
        version: pkg.version.clone(),
        integrity_kind: "local_registry_path".into(),
        status: "ok".into(),
        details: "safe archive paths".into(),
    });

    Ok(("matched".into(), actual, rows))
}

fn index_rel(name: &str) -> PathBuf {
    let n = name.len();
    if n == 1 {
        PathBuf::from(format!("1/{name}"))
    } else if n == 2 {
        PathBuf::from(format!("2/{name}"))
    } else if n == 3 {
        PathBuf::from(format!("3/{}/{name}", &name[..1]))
    } else {
        PathBuf::from(format!("{}/{}/{name}", &name[..2], &name[2..4]))
    }
}

fn walk_files(root: &Path) -> Result<Vec<PathBuf>, AuditorError> {
    let mut out = Vec::new();
    fn rec(dir: &Path, out: &mut Vec<PathBuf>) -> Result<(), AuditorError> {
        for entry in fs::read_dir(dir).map_err(|e| AuditorError::Io(dir.to_path_buf(), e))? {
            let entry = entry.map_err(|e| AuditorError::Io(dir.to_path_buf(), e))?;
            let path = entry.path();
            let meta = fs::symlink_metadata(&path).map_err(|e| AuditorError::Io(path.clone(), e))?;
            if meta.file_type().is_dir() && !meta.file_type().is_symlink() {
                rec(&path, out)?;
            } else {
                out.push(path);
            }
        }
        Ok(())
    }
    rec(root, &mut out)?;
    out.sort();
    Ok(out)
}
