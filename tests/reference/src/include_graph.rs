//! `include` expansion following the Cargo configuration book semantics.

use crate::error::AuditorError;
use crate::input::SolverConfig;
use crate::coalesce::{self, MergeLayer, MergedConfig};
use crate::paths;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

struct IncludeEntry {
    path: String,
    optional: bool,
}

/// Load a config file and its include closure into a single `MergedConfig`.
///
/// Includes are loaded left to right (recursing before finishing the including
/// file); the including file's own values merge on top. Missing optional
/// includes are recorded but non-fatal; missing required includes and cycles
/// reject the request.
#[allow(clippy::too_many_arguments)]
pub fn load_file_with_includes(
    fixture_root: &Path,
    file_path: &Path,
    request_id: &str,
    solver: &SolverConfig,
    include_rows: &mut Vec<crate::report::IncludeRow>,
    depth: u32,
    visiting: &mut BTreeSet<PathBuf>,
    load_order: &mut u32,
) -> Result<MergedConfig, AuditorError> {
    let file_norm = paths::lexical_normalize(file_path);

    if visiting.contains(&file_norm) {
        return Err(coalesce::request_fail(
            request_id,
            "include",
            "include_cycle",
            Some(paths::rel_to(fixture_root, &file_norm)),
            "include cycle detected",
        ));
    }
    if depth > solver.maximum_include_depth {
        return Err(coalesce::request_fail(
            request_id,
            "include",
            "maximum_include_depth_exceeded",
            Some(paths::rel_to(fixture_root, &file_norm)),
            "include depth exceeds solver limit",
        ));
    }

    let table = coalesce::parse_toml_file(&file_norm)?;
    let entries = parse_include_entries(&table);
    let including_dir = file_norm
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));

    visiting.insert(file_norm.clone());
    let mut result = MergedConfig::new();

    for entry in &entries {
        if *load_order == u32::MAX
            || include_rows_count(include_rows, request_id) >= solver.maximum_include_count
        {
            visiting.remove(&file_norm);
            return Err(coalesce::request_fail(
                request_id,
                "include",
                "maximum_include_count_exceeded",
                Some(paths::rel_to(fixture_root, &file_norm)),
                "include count exceeds solver limit",
            ));
        }

        let resolved = paths::lexical_normalize(&including_dir.join(&entry.path));
        let is_toml = entry.path.ends_with(".toml");
        let exists = is_toml && resolved.is_file();

        *load_order += 1;
        include_rows.push(crate::report::IncludeRow {
            request_id: request_id.to_string(),
            including_file: paths::rel_to(fixture_root, &file_norm),
            included_path: paths::rel_to(fixture_root, &resolved),
            optional: entry.optional,
            exists,
            include_depth: depth + 1,
            load_order: *load_order,
        });

        if exists {
            let sub = load_file_with_includes(
                fixture_root,
                &resolved,
                request_id,
                solver,
                include_rows,
                depth + 1,
                visiting,
                load_order,
            )?;
            result.merge_from(sub, MergeLayer::ConfigFile);
        } else if !entry.optional {
            visiting.remove(&file_norm);
            return Err(coalesce::request_fail(
                request_id,
                "include",
                "required_include_missing",
                Some(entry.path.clone()),
                "required include file is missing",
            ));
        }
    }

    // The file's own values (excluding the `include` key) merge on top.
    let mut own = table.clone();
    own.remove("include");
    let path_base = paths::config_path_base(&file_norm);
    let defining_source = paths::rel_to(fixture_root, &file_norm);
    let own_merge = coalesce::merged_from_table(
        &own,
        defining_source,
        Some(path_base),
        MergeLayer::ConfigFile,
        None,
        None,
    );
    result.merge_from(own_merge, MergeLayer::ConfigFile);

    visiting.remove(&file_norm);
    Ok(result)
}

fn include_rows_count(rows: &[crate::report::IncludeRow], request_id: &str) -> u32 {
    rows.iter().filter(|r| r.request_id == request_id).count() as u32
}

fn parse_include_entries(table: &toml::Table) -> Vec<IncludeEntry> {
    let mut out = Vec::new();
    let Some(value) = table.get("include") else {
        return out;
    };
    match value {
        toml::Value::String(s) => out.push(IncludeEntry {
            path: s.clone(),
            optional: false,
        }),
        toml::Value::Table(t) => {
            if let Some(e) = entry_from_table(t) {
                out.push(e);
            }
        }
        toml::Value::Array(a) => {
            for item in a {
                match item {
                    toml::Value::String(s) => out.push(IncludeEntry {
                        path: s.clone(),
                        optional: false,
                    }),
                    toml::Value::Table(t) => {
                        if let Some(e) = entry_from_table(t) {
                            out.push(e);
                        }
                    }
                    _ => {}
                }
            }
        }
        _ => {}
    }
    out
}

fn entry_from_table(t: &toml::Table) -> Option<IncludeEntry> {
    let path = t.get("path")?.as_str()?.to_string();
    let optional = t
        .get("optional")
        .and_then(toml::Value::as_bool)
        .unwrap_or(false);
    Some(IncludeEntry { path, optional })
}
