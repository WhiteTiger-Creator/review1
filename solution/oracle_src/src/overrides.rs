//! `--config` style CLI overrides (inline `KEY=VALUE` and TOML files).

use crate::error::AuditorError;
use crate::input::CliOverride;
use crate::merge::{self, ConfigValue, MergeLayer, MergedConfig, Provenance, ValueCell};
use crate::paths;
use std::path::Path;

/// Apply CLI `--config` overrides in ascending sequence order. Inline overrides
/// are `KEY=VALUE` fragments; file overrides load a TOML file relative to the
/// fixture root.
pub fn apply_cli(
    merged: &mut MergedConfig,
    fixture_root: &Path,
    invocation_dir: &Path,
    rows: &[&CliOverride],
    request_id: &str,
) -> Result<(), AuditorError> {
    for row in rows {
        match row.override_kind.as_str() {
            "inline" => {
                let (key, value) = dotted_to_toml(request_id, &row.value)?;
                merged.insert_merged(
                    key,
                    ValueCell {
                        value,
                        path_base: Some(invocation_dir.to_path_buf()),
                        provenance: Provenance {
                            defining_source: format!("cli:{}", row.sequence),
                            merge_layer: MergeLayer::Cli,
                            environment_override: None,
                            cli_override_sequence: Some(row.sequence),
                        },
                    },
                );
            }
            "file" => {
                let joined = fixture_root.join(&row.value);
                let file_norm = paths::lexical_normalize(&joined);
                if !paths::is_within(fixture_root, &file_norm) {
                    return Err(merge::request_fail(
                        request_id,
                        "cli",
                        "cli_file_path_escape",
                        Some(row.value.clone()),
                        "cli override file escapes fixture root",
                    ));
                }
                if !file_norm.is_file() {
                    return Err(merge::request_fail(
                        request_id,
                        "cli",
                        "cli_file_missing",
                        Some(row.value.clone()),
                        "cli override file is missing",
                    ));
                }
                let table = merge::parse_toml_file(&file_norm)?;
                let mut own = table.clone();
                own.remove("include");
                let path_base = paths::config_path_base(&file_norm);
                let defining_source = paths::rel_to(fixture_root, &file_norm);
                let file_merge = merge::merged_from_table(
                    &own,
                    defining_source,
                    Some(path_base),
                    MergeLayer::Cli,
                    Some(row.sequence),
                    None,
                );
                merged.merge_from(file_merge, MergeLayer::Cli);
            }
            other => {
                return Err(merge::request_fail(
                    request_id,
                    "cli",
                    "unknown_cli_override_kind",
                    Some(other.to_string()),
                    "unknown cli override kind",
                ));
            }
        }
    }
    Ok(())
}

/// Parse an inline `KEY=VALUE` fragment into a flattened dotted key and value.
fn dotted_to_toml(request_id: &str, fragment: &str) -> Result<(String, ConfigValue), AuditorError> {
    let (key, token) = fragment.split_once('=').ok_or_else(|| {
        merge::request_fail(
            request_id,
            "cli",
            "invalid_cli_inline",
            Some(fragment.to_string()),
            "inline override is not KEY=VALUE",
        )
    })?;
    let key = key.trim();
    let token = token.trim();
    if key.is_empty() {
        return Err(merge::request_fail(
            request_id,
            "cli",
            "invalid_cli_inline",
            Some(fragment.to_string()),
            "inline override key is empty",
        ));
    }
    let wrapped = format!("_v = {token}");
    let table: toml::Table = toml::from_str(&wrapped).map_err(|e| {
        merge::request_fail(
            request_id,
            "cli",
            "invalid_cli_inline",
            Some(fragment.to_string()),
            &format!("inline value parse error: {e}"),
        )
    })?;
    let value = table
        .get("_v")
        .map(merge::from_toml_value)
        .ok_or_else(|| {
            merge::request_fail(
                request_id,
                "cli",
                "invalid_cli_inline",
                Some(fragment.to_string()),
                "inline value missing",
            )
        })?;
    Ok((key.to_string(), value))
}
