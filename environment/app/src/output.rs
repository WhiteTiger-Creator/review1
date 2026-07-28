//! Atomic output helpers and stale-file cleanup.

use crate::error::{FatalError, OUTPUT_WRITE_FAILED};
use std::fs;
use std::path::Path;

pub fn remove_stale_output(report_out: &Path) -> Result<(), FatalError> {
    if report_out.exists() {
        fs::remove_file(report_out).map_err(|err| {
            FatalError::new(
                OUTPUT_WRITE_FAILED,
                format!("remove {}: {err}", report_out.display()),
            )
        })?;
    }
    let tmp = temp_sibling(report_out);
    if tmp.exists() {
        let _ = fs::remove_file(tmp);
    }
    Ok(())
}

pub fn atomic_write(report_out: &Path, bytes: &[u8]) -> Result<(), FatalError> {
    if let Some(parent) = report_out.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            FatalError::new(OUTPUT_WRITE_FAILED, err.to_string())
        })?;
    }
    let tmp = temp_sibling(report_out);
    fs::write(&tmp, bytes).map_err(|err| {
        FatalError::new(
            OUTPUT_WRITE_FAILED,
            format!("write {}: {err}", tmp.display()),
        )
    })?;
    fs::rename(&tmp, report_out).map_err(|err| {
        let _ = fs::remove_file(&tmp);
        FatalError::new(
            OUTPUT_WRITE_FAILED,
            format!("rename {}: {err}", report_out.display()),
        )
    })
}

fn temp_sibling(path: &Path) -> std::path::PathBuf {
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("output");
    path.with_file_name(format!("{file_name}.tmp"))
}
