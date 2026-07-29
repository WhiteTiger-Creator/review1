//! Input loaders for the audit request set and configuration profiles.

use crate::error::AuditorError;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::Path;

#[derive(Debug, Clone, Deserialize)]
pub struct Request {
    pub request_id: String,
    pub invocation_directory: String,
    pub environment_profile_id: String,
    pub cli_override_profile_id: String,
    pub workspace_manifest: String,
    pub existing_lock: String,
    #[serde(default)]
    pub run_build: bool,
    #[allow(dead_code)]
    #[serde(default)]
    pub output_report_name: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EnvProfile {
    pub profile_id: String,
    #[serde(default)]
    pub variables: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EnvironmentOverrides {
    #[allow(dead_code)]
    #[serde(default)]
    pub schema_version: Option<u64>,
    #[serde(default)]
    pub profiles: Vec<EnvProfile>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CliOverride {
    pub profile_id: String,
    pub sequence: u32,
    pub override_kind: String,
    pub value: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceProfile {
    #[allow(dead_code)]
    pub source_name: String,
    #[allow(dead_code)]
    pub source_kind: String,
    #[allow(dead_code)]
    pub root_path: String,
    #[allow(dead_code)]
    pub expected_source_id: String,
    #[allow(dead_code)]
    pub checksum_algorithm: String,
    #[allow(dead_code)]
    pub package_name: String,
    #[allow(dead_code)]
    pub package_version: String,
    #[allow(dead_code)]
    pub package_checksum: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceProfiles {
    #[serde(default)]
    #[allow(dead_code)]
    pub profiles: Vec<SourceProfile>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SolverConfig {
    pub maximum_include_depth: u32,
    pub maximum_include_count: u32,
    #[allow(dead_code)]
    pub maximum_replacement_depth: u32,
    #[allow(dead_code)]
    pub maximum_config_file_size_bytes: u64,
    #[allow(dead_code)]
    pub maximum_source_package_count: u64,
    #[allow(dead_code)]
    #[serde(default)]
    pub output_decimal_places: u32,
}

fn read_to_string(path: &Path) -> Result<String, AuditorError> {
    std::fs::read_to_string(path).map_err(|e| AuditorError::Io(path.to_path_buf(), e))
}

fn parse_ndjson<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<Vec<T>, AuditorError> {
    let text = read_to_string(path)?;
    let mut out = Vec::new();
    for (idx, line) in text.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let parsed: T = serde_json::from_str(trimmed).map_err(|e| {
            AuditorError::Fatal(format!("{} line {}: {e}", path.display(), idx + 1))
        })?;
        out.push(parsed);
    }
    Ok(out)
}

fn parse_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, AuditorError> {
    let text = read_to_string(path)?;
    serde_json::from_str(&text)
        .map_err(|e| AuditorError::Fatal(format!("{}: {e}", path.display())))
}

pub fn load_requests(path: &Path) -> Result<Vec<Request>, AuditorError> {
    parse_ndjson(path)
}

pub fn load_environment_overrides(path: &Path) -> Result<EnvironmentOverrides, AuditorError> {
    parse_json(path)
}

pub fn load_cli_overrides(path: &Path) -> Result<Vec<CliOverride>, AuditorError> {
    parse_ndjson(path)
}

pub fn load_source_profiles(path: &Path) -> Result<SourceProfiles, AuditorError> {
    parse_json(path)
}

pub fn load_solver_config(path: &Path) -> Result<SolverConfig, AuditorError> {
    parse_json(path)
}
