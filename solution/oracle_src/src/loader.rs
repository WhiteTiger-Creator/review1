//! Load JSON and NDJSON inputs from a data directory.

use crate::error::{FatalError, MALFORMED_JSON, MISSING_REQUIRED_INPUT};
use crate::models::{
    DeclarationsDoc, LoadedData, PackageCandidatesDoc, PolicyDoc, PreviousLocksDoc,
    ProviderResponsesDoc, SourceOverridesDoc, TargetGraphDoc,
};
use serde::de::DeserializeOwned;
use std::fs;
use std::path::{Path, PathBuf};

pub const REQUIRED_FILES: &[&str] = &[
    "declarations.json",
    "find_requests.ndjson",
    "provider_responses.json",
    "package_candidates.json",
    "source_overrides.json",
    "target_graph.json",
    "previous_resolution_locks.json",
    "policy.json",
];

pub fn required_files_exist(data_dir: &Path) -> Result<(), FatalError> {
    let missing: Vec<String> = REQUIRED_FILES
        .iter()
        .filter(|name| !data_dir.join(name).is_file())
        .map(|name| (*name).to_string())
        .collect();
    if !missing.is_empty() {
        let mut names = missing;
        names.sort();
        return Err(FatalError::new(
            MISSING_REQUIRED_INPUT,
            names.join(","),
        ));
    }
    Ok(())
}

pub fn load_data_dir(data_dir: &Path) -> Result<LoadedData, FatalError> {
    required_files_exist(data_dir)?;

    let declarations = read_json::<DeclarationsDoc>(data_dir, "declarations.json")?.declarations;
    let provider_doc = read_json::<ProviderResponsesDoc>(data_dir, "provider_responses.json")?;
    let candidates =
        read_json::<PackageCandidatesDoc>(data_dir, "package_candidates.json")?.candidates;
    let overrides = read_json::<SourceOverridesDoc>(data_dir, "source_overrides.json")?.overrides;
    let target_graph = read_json::<TargetGraphDoc>(data_dir, "target_graph.json")?;
    let locks = read_json::<PreviousLocksDoc>(data_dir, "previous_resolution_locks.json")?.locks;
    let policy = read_json::<PolicyDoc>(data_dir, "policy.json")?;
    let find_requests = read_ndjson(data_dir.join("find_requests.ndjson"))?;

    Ok(LoadedData {
        declarations,
        find_requests,
        providers: provider_doc.providers,
        provider_responses: provider_doc.responses,
        candidates,
        overrides,
        target_graph,
        locks,
        policy,
    })
}

fn read_json<T: DeserializeOwned>(data_dir: &Path, file_name: &str) -> Result<T, FatalError> {
    let path = data_dir.join(file_name);
    let bytes = fs::read(&path).map_err(|_| {
        FatalError::new(MISSING_REQUIRED_INPUT, path.display().to_string())
    })?;
    parse_json_bytes(&bytes, &path)
}

fn parse_json_bytes<T: DeserializeOwned>(bytes: &[u8], path: &Path) -> Result<T, FatalError> {
    serde_json::from_slice(bytes).map_err(|_| {
        FatalError::new(MALFORMED_JSON, path.display().to_string())
    })
}

fn read_ndjson(path: PathBuf) -> Result<Vec<crate::models::FindRequest>, FatalError> {
    let bytes = fs::read(&path).map_err(|_| {
        FatalError::new(MISSING_REQUIRED_INPUT, path.display().to_string())
    })?;
    let text = String::from_utf8_lossy(&bytes);
    let mut rows = Vec::new();
    for (line_no, line) in text.lines().enumerate() {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        let value: serde_json::Value = serde_json::from_str(stripped).map_err(|_| {
            FatalError::new(MALFORMED_JSON, format!("{}:{line_no}", path.display()))
        })?;
        if !value.is_object() {
            return Err(FatalError::new(
                MALFORMED_JSON,
                format!("{}:{line_no}", path.display()),
            ));
        }
        let row: crate::models::FindRequest = serde_json::from_value(value).map_err(|_| {
            FatalError::new(MALFORMED_JSON, format!("{}:{line_no}", path.display()))
        })?;
        rows.push(row);
    }
    Ok(rows)
}
