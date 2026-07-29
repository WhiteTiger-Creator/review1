use crate::error::AuditorError;
use serde::Serialize;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

#[derive(Debug, Default, Serialize)]
pub struct Report {
    pub request_rows: Vec<RequestRow>,
    pub discovered_config_rows: Vec<DiscoveredConfigRow>,
    pub include_rows: Vec<IncludeRow>,
    pub effective_value_rows: Vec<EffectiveValueRow>,
    pub path_resolution_rows: Vec<PathResolutionRow>,
    pub source_rows: Vec<SourceRow>,
    pub replacement_edge_rows: Vec<ReplacementEdgeRow>,
    pub package_source_rows: Vec<PackageSourceRow>,
    pub lock_reconciliation_rows: Vec<LockReconciliationRow>,
    pub integrity_rows: Vec<IntegrityRow>,
    pub build_rows: Vec<BuildRow>,
    pub rejection_rows: Vec<RejectionRow>,
    pub summary: Summary,
}

#[derive(Debug, Clone, Serialize)]
pub struct RequestRow {
    pub request_id: String,
    pub invocation_directory: String,
    pub status: String,
    pub reason_or_null: Option<String>,
    pub discovered_config_count: u32,
    pub include_count: u32,
    pub effective_value_count: u32,
    pub terminal_source_count: u32,
    pub build_status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiscoveredConfigRow {
    pub request_id: String,
    pub config_path: String,
    pub discovery_depth: u32,
    pub load_order: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct IncludeRow {
    pub request_id: String,
    pub including_file: String,
    pub included_path: String,
    pub optional: bool,
    pub exists: bool,
    pub include_depth: u32,
    pub load_order: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct EffectiveValueRow {
    pub request_id: String,
    pub key: String,
    pub value_type: String,
    pub canonical_value: String,
    pub defining_source: String,
    pub merge_layer: String,
    pub environment_override_or_null: Option<String>,
    pub cli_override_sequence_or_null: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PathResolutionRow {
    pub request_id: String,
    pub key: String,
    pub raw_path: String,
    pub base_path: String,
    pub normalized_path: String,
    pub exists: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct SourceRow {
    pub request_id: String,
    pub source_name: String,
    pub source_kind: String,
    pub replace_with_or_null: Option<String>,
    pub terminal_source: String,
    pub root_path_or_null: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReplacementEdgeRow {
    pub request_id: String,
    pub from_source: String,
    pub to_source: String,
    pub edge_index: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct PackageSourceRow {
    pub request_id: String,
    pub package_name: String,
    pub version: String,
    pub original_source: String,
    pub terminal_source: String,
    pub relative_package_path: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LockReconciliationRow {
    pub request_id: String,
    pub package_name: String,
    pub version: String,
    pub lock_source: String,
    pub effective_source: String,
    pub checksum: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct IntegrityRow {
    pub request_id: String,
    pub source_name: String,
    pub package_name: String,
    pub version: String,
    pub integrity_kind: String,
    pub status: String,
    pub details: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BuildRow {
    pub request_id: String,
    pub status: String,
    pub exit_code: i32,
    pub lock_unchanged: bool,
    pub source_bytes_unchanged: bool,
    pub artifact_count: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct RejectionRow {
    pub request_id: String,
    pub stage: String,
    pub reason: String,
    pub path_or_source_or_null: Option<String>,
    pub details: String,
}

#[derive(Debug, Default, Clone, Serialize)]
pub struct Summary {
    pub request_count: u32,
    pub accepted_request_count: u32,
    pub rejected_request_count: u32,
    pub discovered_config_count: u32,
    pub include_count: u32,
    pub effective_source_count: u32,
    pub verified_package_count: u32,
    pub successful_build_count: u32,
    pub failed_build_count: u32,
}

impl Report {
    pub fn finalize_summary(&mut self) {
        self.summary.request_count = self.request_rows.len() as u32;
        self.summary.accepted_request_count = self
            .request_rows
            .iter()
            .filter(|r| r.status == "accepted")
            .count() as u32;
        self.summary.rejected_request_count = self
            .request_rows
            .iter()
            .filter(|r| r.status == "rejected")
            .count() as u32;
        self.summary.discovered_config_count = self.discovered_config_rows.len() as u32;
        self.summary.include_count = self.include_rows.len() as u32;
        self.summary.effective_source_count = self
            .source_rows
            .iter()
            .filter(|s| s.replace_with_or_null.is_none())
            .count() as u32;
        self.summary.verified_package_count = self
            .lock_reconciliation_rows
            .iter()
            .filter(|r| r.status == "matched")
            .count() as u32;
        self.summary.successful_build_count = self
            .build_rows
            .iter()
            .filter(|b| b.status == "success")
            .count() as u32;
        self.summary.failed_build_count = self
            .build_rows
            .iter()
            .filter(|b| b.status == "failed")
            .count() as u32;
    }

    pub fn sort_all(&mut self) {
        self.request_rows.sort_by(|a, b| a.request_id.cmp(&b.request_id));
        self.discovered_config_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.load_order, a.config_path.as_str()).cmp(&(
                b.request_id.as_str(),
                b.load_order,
                b.config_path.as_str(),
            ))
        });
        self.include_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.load_order, a.included_path.as_str()).cmp(&(
                b.request_id.as_str(),
                b.load_order,
                b.included_path.as_str(),
            ))
        });
        self.effective_value_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.key.as_str()).cmp(&(b.request_id.as_str(), b.key.as_str()))
        });
        self.path_resolution_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.key.as_str()).cmp(&(b.request_id.as_str(), b.key.as_str()))
        });
        self.source_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.source_name.as_str())
                .cmp(&(b.request_id.as_str(), b.source_name.as_str()))
        });
        self.replacement_edge_rows.sort_by(|a, b| {
            (
                a.request_id.as_str(),
                a.from_source.as_str(),
                a.edge_index,
                a.to_source.as_str(),
            )
                .cmp(&(
                    b.request_id.as_str(),
                    b.from_source.as_str(),
                    b.edge_index,
                    b.to_source.as_str(),
                ))
        });
        self.package_source_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.package_name.as_str(), a.version.as_str()).cmp(&(
                b.request_id.as_str(),
                b.package_name.as_str(),
                b.version.as_str(),
            ))
        });
        self.lock_reconciliation_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.package_name.as_str(), a.version.as_str()).cmp(&(
                b.request_id.as_str(),
                b.package_name.as_str(),
                b.version.as_str(),
            ))
        });
        self.integrity_rows.sort_by(|a, b| {
            (
                a.request_id.as_str(),
                a.package_name.as_str(),
                a.version.as_str(),
                a.integrity_kind.as_str(),
                a.details.as_str(),
            )
                .cmp(&(
                    b.request_id.as_str(),
                    b.package_name.as_str(),
                    b.version.as_str(),
                    b.integrity_kind.as_str(),
                    b.details.as_str(),
                ))
        });
        self.build_rows
            .sort_by(|a, b| a.request_id.cmp(&b.request_id));
        self.rejection_rows.sort_by(|a, b| {
            (a.request_id.as_str(), a.stage.as_str(), a.reason.as_str()).cmp(&(
                b.request_id.as_str(),
                b.stage.as_str(),
                b.reason.as_str(),
            ))
        });
    }
}

pub fn write_atomic(path: &Path, report: &Report) -> Result<(), AuditorError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| AuditorError::Io(parent.to_path_buf(), e))?;
    }
    let tmp = PathBuf::from(format!("{}.tmp", path.display()));
    let json = serde_json::to_string_pretty(report)
        .map_err(|e| AuditorError::Fatal(format!("serialize report: {e}")))?;
    {
        let mut f = fs::File::create(&tmp).map_err(|e| AuditorError::Io(tmp.clone(), e))?;
        f.write_all(json.as_bytes())
            .map_err(|e| AuditorError::Io(tmp.clone(), e))?;
        f.write_all(b"\n")
            .map_err(|e| AuditorError::Io(tmp.clone(), e))?;
        f.sync_all()
            .map_err(|e| AuditorError::Io(tmp.clone(), e))?;
    }
    fs::rename(&tmp, path).map_err(|e| AuditorError::Io(path.to_path_buf(), e))?;
    Ok(())
}
