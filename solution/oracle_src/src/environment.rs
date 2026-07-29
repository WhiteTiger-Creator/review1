//! Environment variable overrides for the bounded profile key set.

use crate::error::AuditorError;
use crate::input::EnvProfile;
use crate::merge::{self, ConfigValue, MergeLayer, MergedConfig, Provenance, ValueCell};
use std::path::Path;

enum EnvType {
    Int,
    Bool,
    Str,
}

fn mapping(env_key: &str) -> Option<(&'static str, EnvType)> {
    match env_key {
        "CARGO_BUILD_JOBS" => Some(("build.jobs", EnvType::Int)),
        "CARGO_BUILD_INCREMENTAL" => Some(("build.incremental", EnvType::Bool)),
        "CARGO_NET_OFFLINE" => Some(("net.offline", EnvType::Bool)),
        "CARGO_TERM_QUIET" => Some(("term.quiet", EnvType::Bool)),
        "CARGO_TERM_VERBOSE" => Some(("term.verbose", EnvType::Bool)),
        "CARGO_TERM_COLOR" => Some(("term.color", EnvType::Str)),
        _ => None,
    }
}

/// Apply an environment profile on top of the merged config. Unknown variables
/// are ignored; malformed typed values reject the request.
pub fn apply_env(
    merged: &mut MergedConfig,
    profile: &EnvProfile,
    invocation_dir: &Path,
) -> Result<(), AuditorError> {
    for (env_key, raw) in profile.variables.iter() {
        let Some((key, ty)) = mapping(env_key) else {
            continue;
        };
        let value = match ty {
            EnvType::Int => {
                let n: i64 = raw.trim().parse().map_err(|_| {
                    merge::request_fail(
                        "",
                        "environment",
                        "invalid_environment_value",
                        Some(format!("{env_key}={raw}")),
                        "environment value is not an integer",
                    )
                })?;
                ConfigValue::Integer(n)
            }
            EnvType::Bool => match raw.trim() {
                "true" => ConfigValue::Boolean(true),
                "false" => ConfigValue::Boolean(false),
                _ => {
                    return Err(merge::request_fail(
                        "",
                        "environment",
                        "invalid_environment_value",
                        Some(format!("{env_key}={raw}")),
                        "environment value is not a boolean",
                    ));
                }
            },
            EnvType::Str => ConfigValue::String(raw.clone()),
        };

        merged.insert_merged(
            key.to_string(),
            ValueCell {
                value,
                path_base: Some(invocation_dir.to_path_buf()),
                provenance: Provenance {
                    defining_source: "environment".to_string(),
                    merge_layer: MergeLayer::Environment,
                    environment_override: Some(env_key.clone()),
                    cli_override_sequence: None,
                },
            },
        );
    }
    Ok(())
}
