//! Layered merge of bounded Cargo configuration with per-leaf provenance.

use crate::error::{AuditorError, RequestFailure};
use crate::report::EffectiveValueRow;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Supported bounded TOML value kinds.
#[derive(Debug, Clone)]
pub enum ConfigValue {
    String(String),
    Integer(i64),
    Boolean(bool),
    Array(Vec<ConfigValue>),
    Table(BTreeMap<String, ConfigValue>),
}

/// Which precedence layer produced (or last touched) a value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MergeLayer {
    ConfigFile,
    Environment,
    Cli,
}

impl MergeLayer {
    pub fn as_str(&self) -> &'static str {
        match self {
            MergeLayer::ConfigFile => "config_file",
            MergeLayer::Environment => "environment",
            MergeLayer::Cli => "cli",
        }
    }
}

/// Provenance metadata carried by every effective leaf value.
#[derive(Debug, Clone)]
pub struct Provenance {
    pub defining_source: String,
    pub merge_layer: MergeLayer,
    pub environment_override: Option<String>,
    pub cli_override_sequence: Option<u32>,
}

/// A single merged leaf: its value, the path base to use for path-bearing keys,
/// and its provenance.
#[derive(Debug, Clone)]
pub struct ValueCell {
    pub value: ConfigValue,
    pub path_base: Option<PathBuf>,
    pub provenance: Provenance,
}

/// Flattened dotted-key view of the effective configuration.
#[derive(Debug, Default)]
pub struct MergedConfig {
    pub values: BTreeMap<String, ValueCell>,
}

impl MergedConfig {
    pub fn new() -> Self {
        MergedConfig {
            values: BTreeMap::new(),
        }
    }

    /// Merge every leaf of `other` into `self` under `layer`. Later contributions
    /// win for scalars; arrays concatenate with later items at higher precedence.
    pub fn merge_from(&mut self, other: MergedConfig, layer: MergeLayer) {
        for (key, mut cell) in other.values {
            cell.provenance.merge_layer = layer.clone();
            self.insert_merged(key, cell);
        }
    }

    /// Insert a single leaf, applying scalar-replace / array-concatenate rules.
    pub fn insert_merged(&mut self, key: String, cell: ValueCell) {
        match self.values.get_mut(&key) {
            Some(existing) => {
                if let (ConfigValue::Array(ex), ConfigValue::Array(new)) =
                    (&existing.value, &cell.value)
                {
                    let mut combined = ex.clone();
                    combined.extend(new.clone());
                    existing.value = ConfigValue::Array(combined);
                    existing.provenance = cell.provenance;
                    if cell.path_base.is_some() {
                        existing.path_base = cell.path_base;
                    }
                } else {
                    *existing = cell;
                }
            }
            None => {
                self.values.insert(key, cell);
            }
        }
    }

    /// Emit report rows for the bounded effective-value key set.
    pub fn effective_value_rows(&self, request_id: &str) -> Vec<EffectiveValueRow> {
        let mut rows = Vec::new();
        for (key, cell) in &self.values {
            if !is_bounded_effective_key(key) {
                continue;
            }
            rows.push(EffectiveValueRow {
                request_id: request_id.to_string(),
                key: key.clone(),
                value_type: value_type_of(&cell.value).to_string(),
                canonical_value: canonical_of(&cell.value),
                defining_source: cell.provenance.defining_source.clone(),
                merge_layer: cell.provenance.merge_layer.as_str().to_string(),
                environment_override_or_null: cell.provenance.environment_override.clone(),
                cli_override_sequence_or_null: cell.provenance.cli_override_sequence,
            });
        }
        rows.sort_by(|a, b| a.key.cmp(&b.key));
        rows
    }
}

/// True for keys reported in `effective_value_rows`.
pub fn is_bounded_effective_key(key: &str) -> bool {
    matches!(
        key,
        "build.jobs"
            | "build.incremental"
            | "build.rustflags"
            | "build.target-dir"
            | "net.offline"
            | "term.quiet"
            | "term.verbose"
            | "term.color"
    ) || (key.starts_with("source.")
        && (key.ends_with(".replace-with")
            || key.ends_with(".directory")
            || key.ends_with(".local-registry")))
}

/// Convert a `toml::Value` into a bounded `ConfigValue`.
pub fn from_toml_value(value: &toml::Value) -> ConfigValue {
    match value {
        toml::Value::String(s) => ConfigValue::String(s.clone()),
        toml::Value::Integer(i) => ConfigValue::Integer(*i),
        toml::Value::Boolean(b) => ConfigValue::Boolean(*b),
        toml::Value::Float(f) => ConfigValue::String(f.to_string()),
        toml::Value::Datetime(d) => ConfigValue::String(d.to_string()),
        toml::Value::Array(a) => ConfigValue::Array(a.iter().map(from_toml_value).collect()),
        toml::Value::Table(t) => {
            let mut map = BTreeMap::new();
            for (k, v) in t.iter() {
                map.insert(k.clone(), from_toml_value(v));
            }
            ConfigValue::Table(map)
        }
    }
}

/// Flatten a TOML table into dotted leaf keys. Arrays are treated as leaves.
pub fn flatten_toml(table: &toml::Table) -> BTreeMap<String, ConfigValue> {
    fn rec(prefix: &str, table: &toml::Table, out: &mut BTreeMap<String, ConfigValue>) {
        for (k, v) in table.iter() {
            let key = if prefix.is_empty() {
                k.clone()
            } else {
                format!("{prefix}.{k}")
            };
            match v {
                toml::Value::Table(inner) => rec(&key, inner, out),
                other => {
                    out.insert(key, from_toml_value(other));
                }
            }
        }
    }
    let mut out = BTreeMap::new();
    rec("", table, &mut out);
    out
}

/// Parse a TOML file into a table, reporting IO/parse problems as fatal.
pub fn parse_toml_file(path: &Path) -> Result<toml::Table, AuditorError> {
    let text = std::fs::read_to_string(path).map_err(|e| AuditorError::Io(path.to_path_buf(), e))?;
    toml::from_str::<toml::Table>(&text)
        .map_err(|e| AuditorError::Fatal(format!("toml parse {}: {e}", path.display())))
}

/// Build a `MergedConfig` from a parsed config table for a single file.
pub fn merged_from_table(
    table: &toml::Table,
    defining_source: String,
    path_base: Option<PathBuf>,
    layer: MergeLayer,
    cli_sequence: Option<u32>,
    environment_override: Option<String>,
) -> MergedConfig {
    let mut mc = MergedConfig::new();
    for (key, value) in flatten_toml(table) {
        mc.values.insert(
            key,
            ValueCell {
                value,
                path_base: path_base.clone(),
                provenance: Provenance {
                    defining_source: defining_source.clone(),
                    merge_layer: layer.clone(),
                    environment_override: environment_override.clone(),
                    cli_override_sequence: cli_sequence,
                },
            },
        );
    }
    mc
}

/// Reported value-type discriminant string.
pub fn value_type_of(value: &ConfigValue) -> &'static str {
    match value {
        ConfigValue::String(_) => "string",
        ConfigValue::Integer(_) => "integer",
        ConfigValue::Boolean(_) => "boolean",
        ConfigValue::Array(_) => "array",
        ConfigValue::Table(_) => "table",
    }
}

/// Canonical string form for report emission.
pub fn canonical_of(value: &ConfigValue) -> String {
    match value {
        ConfigValue::String(s) => s.clone(),
        ConfigValue::Integer(i) => i.to_string(),
        ConfigValue::Boolean(b) => b.to_string(),
        ConfigValue::Array(_) | ConfigValue::Table(_) => {
            serde_json::to_string(&to_json(value)).unwrap_or_default()
        }
    }
}

fn to_json(value: &ConfigValue) -> serde_json::Value {
    match value {
        ConfigValue::String(s) => serde_json::Value::String(s.clone()),
        ConfigValue::Integer(i) => serde_json::Value::Number((*i).into()),
        ConfigValue::Boolean(b) => serde_json::Value::Bool(*b),
        ConfigValue::Array(a) => serde_json::Value::Array(a.iter().map(to_json).collect()),
        ConfigValue::Table(t) => {
            let mut map = serde_json::Map::new();
            for (k, v) in t.iter() {
                map.insert(k.clone(), to_json(v));
            }
            serde_json::Value::Object(map)
        }
    }
}

/// Construct a per-request failure error.
pub fn request_fail(
    request_id: &str,
    stage: &str,
    reason: &str,
    path_or_source: Option<String>,
    details: &str,
) -> AuditorError {
    AuditorError::Request(RequestFailure {
        request_id: request_id.to_string(),
        stage: stage.to_string(),
        reason: reason.to_string(),
        path_or_source,
        details: details.to_string(),
    })
}
