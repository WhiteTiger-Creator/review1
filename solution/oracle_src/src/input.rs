use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use rusqlite::Connection;
use serde_json::Value as JsonValue;
use serde_yaml::Value as YamlValue;

use crate::checksum::{
    compute_runbook_checksum, normalize_content_type, normalize_method, sort_utf8, unique_array,
    validate_checksum_syntax,
};
use crate::error::{FatalInputError, Result};
use crate::model::{
    step_kind_to_mode, ApiOperation, Deployment, PlannerInputs, ReleaseProfile, ReleaseRequest,
    Runbook, Step,
};

fn yaml_get<'a>(map: &'a serde_yaml::Mapping, key: &str) -> Result<&'a YamlValue> {
    map.get(&YamlValue::String(key.to_string()))
        .ok_or_else(|| FatalInputError::new("malformed YAML"))
}

fn yaml_string(value: &YamlValue) -> Result<String> {
    value
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| FatalInputError::new("malformed YAML"))
}

fn yaml_i64(value: &YamlValue) -> Result<i64> {
    if let Some(v) = value.as_i64() {
        return Ok(v);
    }
    if let Some(v) = value.as_u64() {
        return Ok(v as i64);
    }
    Err(FatalInputError::new("malformed YAML"))
}

fn yaml_string_list(value: &YamlValue) -> Result<Vec<String>> {
    match value {
        YamlValue::Sequence(seq) => seq.iter().map(yaml_string).collect(),
        YamlValue::Null => Ok(Vec::new()),
        _ => Err(FatalInputError::new("malformed YAML")),
    }
}

fn yaml_i64_list(value: &YamlValue) -> Result<Vec<i64>> {
    match value {
        YamlValue::Sequence(seq) => seq.iter().map(yaml_i64).collect(),
        YamlValue::Null => Ok(Vec::new()),
        _ => Err(FatalInputError::new("malformed YAML")),
    }
}

fn yaml_nullable_string(value: &YamlValue) -> Result<Option<String>> {
    if value.is_null() {
        return Ok(None);
    }
    Ok(Some(yaml_string(value)?))
}

fn parse_step(raw: &YamlValue) -> Result<Step> {
    let map = match raw {
        YamlValue::Mapping(m) => m,
        _ => return Err(FatalInputError::new("malformed YAML")),
    };
    let allowed: HashSet<&str> = [
        "step_id",
        "step_rank",
        "step_kind",
        "requires_step_ids",
        "required_capabilities",
        "provided_capabilities",
        "api_operation_id_or_null",
        "http_method_or_null",
        "request_content_type_or_null",
        "accepted_statuses",
        "database_action_or_null",
        "retry_mode",
        "idempotency_key_source_or_null",
    ]
    .into_iter()
    .collect();
    let keys: HashSet<String> = map
        .keys()
        .filter_map(|k| k.as_str().map(str::to_string))
        .collect();
    let mut unknown: Vec<String> = keys
        .iter()
        .filter(|k| !allowed.contains(k.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        unknown.sort();
        return Err(FatalInputError::new(format!(
            "unknown step fields: {unknown:?}"
        )));
    }
    for field in [
        "requires_step_ids",
        "required_capabilities",
        "provided_capabilities",
    ] {
        unique_array(&yaml_string_list(yaml_get(map, field)?)?)?;
    }
    let kind = yaml_string(yaml_get(map, "step_kind")?)?;
    if step_kind_to_mode(&kind).is_none() {
        return Err(FatalInputError::new("invalid step-kind token"));
    }
    let retry = yaml_string(yaml_get(map, "retry_mode")?)?;
    if !["never", "safe", "idempotency_key_required"].contains(&retry.as_str()) {
        return Err(FatalInputError::new("invalid retry-mode token"));
    }
    let is_api = kind == "api_request";
    let api_op = yaml_nullable_string(yaml_get(map, "api_operation_id_or_null")?)?;
    let http_method = yaml_nullable_string(yaml_get(map, "http_method_or_null")?)?;
    let content_type = yaml_nullable_string(yaml_get(map, "request_content_type_or_null")?)?;
    let accepted_statuses = yaml_i64_list(yaml_get(map, "accepted_statuses")?)?;
    let db_action = yaml_nullable_string(yaml_get(map, "database_action_or_null")?)?;
    if is_api {
        if api_op.is_none()
            || http_method.is_none()
            || content_type.is_none()
            || accepted_statuses.is_empty()
            || db_action.is_some()
        {
            return Err(FatalInputError::new("invalid step field combination"));
        }
    } else if api_op.is_some()
        || http_method.is_some()
        || content_type.is_some()
        || !accepted_statuses.is_empty()
    {
        return Err(FatalInputError::new("invalid step field combination"));
    }
    Ok(Step {
        step_id: yaml_string(yaml_get(map, "step_id")?)?,
        step_rank: yaml_i64(yaml_get(map, "step_rank")?)?,
        step_kind: kind,
        requires_step_ids: yaml_string_list(yaml_get(map, "requires_step_ids")?)?,
        required_capabilities: yaml_string_list(yaml_get(map, "required_capabilities")?)?,
        provided_capabilities: yaml_string_list(yaml_get(map, "provided_capabilities")?)?,
        api_operation_id_or_null: api_op,
        http_method_or_null: http_method,
        request_content_type_or_null: content_type,
        accepted_statuses,
        database_action_or_null: db_action,
        retry_mode: retry,
        idempotency_key_source_or_null: yaml_nullable_string(yaml_get(
            map,
            "idempotency_key_source_or_null",
        )?)?,
    })
}

fn parse_runbook(raw: &YamlValue) -> Result<Runbook> {
    let map = match raw {
        YamlValue::Mapping(m) => m,
        _ => return Err(FatalInputError::new("malformed YAML")),
    };
    let allowed: HashSet<&str> = [
        "runbook_id",
        "version",
        "checksum_sha256",
        "plan_rank",
        "requires",
        "conflicts",
        "replaces",
        "provides_runbook_ids",
        "allowed_api_revisions",
        "allowed_database_revisions",
        "steps",
    ]
    .into_iter()
    .collect();
    let keys: HashSet<String> = map
        .keys()
        .filter_map(|k| k.as_str().map(str::to_string))
        .collect();
    let unknown: Vec<String> = keys
        .iter()
        .filter(|k| !allowed.contains(k.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        let mut sorted = unknown;
        sorted.sort();
        return Err(FatalInputError::new(format!(
            "unknown runbook fields: {sorted:?}"
        )));
    }
    for field in [
        "requires",
        "conflicts",
        "replaces",
        "provides_runbook_ids",
        "allowed_api_revisions",
        "allowed_database_revisions",
    ] {
        unique_array(&yaml_string_list(yaml_get(map, field)?)?)?;
    }
    let checksum = yaml_string(yaml_get(map, "checksum_sha256")?)?;
    if !validate_checksum_syntax(&checksum) {
        return Err(FatalInputError::new("invalid checksum syntax"));
    }
    let steps_raw = yaml_get(map, "steps")?;
    let steps_seq = match steps_raw {
        YamlValue::Sequence(seq) => seq,
        _ => return Err(FatalInputError::new("malformed YAML")),
    };
    if steps_seq.is_empty() {
        return Err(FatalInputError::new("empty steps"));
    }
    let mut steps = Vec::new();
    let mut seen_steps = HashSet::new();
    for item in steps_seq {
        let step = parse_step(item)?;
        if !seen_steps.insert(step.step_id.clone()) {
            return Err(FatalInputError::new("duplicate step ID"));
        }
        steps.push(step);
    }
    Ok(Runbook {
        runbook_id: yaml_string(yaml_get(map, "runbook_id")?)?,
        version: yaml_string(yaml_get(map, "version")?)?,
        checksum_sha256: checksum,
        plan_rank: yaml_i64(yaml_get(map, "plan_rank")?)?,
        requires: yaml_string_list(yaml_get(map, "requires")?)?,
        conflicts: yaml_string_list(yaml_get(map, "conflicts")?)?,
        replaces: yaml_string_list(yaml_get(map, "replaces")?)?,
        provides_runbook_ids: yaml_string_list(yaml_get(map, "provides_runbook_ids")?)?,
        allowed_api_revisions: yaml_string_list(yaml_get(map, "allowed_api_revisions")?)?,
        allowed_database_revisions: yaml_string_list(yaml_get(map, "allowed_database_revisions")?)?,
        steps,
    })
}

pub fn load_runbooks(runbooks_dir: &Path) -> Result<HashMap<String, Runbook>> {
    let mut paths: Vec<_> = fs::read_dir(runbooks_dir)
        .map_err(|_| FatalInputError::new("malformed YAML"))?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("yaml"))
        .collect();
    paths.sort_by(|a, b| {
        a.file_name()
            .unwrap()
            .as_encoded_bytes()
            .cmp(b.file_name().unwrap().as_encoded_bytes())
    });
    let mut runbooks = HashMap::new();
    for path in paths {
        let text = fs::read_to_string(&path).map_err(|_| FatalInputError::new("malformed YAML"))?;
        let raw: YamlValue =
            serde_yaml::from_str(&text).map_err(|_| FatalInputError::new("malformed YAML"))?;
        if !raw.is_mapping() {
            return Err(FatalInputError::new(format!(
                "malformed YAML in {}",
                path.display()
            )));
        }
        let rb = parse_runbook(&raw)?;
        if runbooks.contains_key(&rb.runbook_id) {
            return Err(FatalInputError::new(format!(
                "duplicate runbook ID {}",
                rb.runbook_id
            )));
        }
        if compute_runbook_checksum(&rb) != rb.checksum_sha256 {
            return Err(FatalInputError::new("runbook_checksum_mismatch"));
        }
        runbooks.insert(rb.runbook_id.clone(), rb);
    }
    Ok(runbooks)
}

pub fn load_profile(path: &Path) -> Result<ReleaseProfile> {
    let text = fs::read_to_string(path)
        .map_err(|_| FatalInputError::new("invalid release-profile structure"))?;
    let raw: toml::Value = text
        .parse()
        .map_err(|_| FatalInputError::new("invalid release-profile structure"))?;
    let table = raw
        .as_table()
        .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?;
    let allowed: HashSet<&str> = [
        "release_profile_version",
        "maximum_runbooks_per_request",
        "maximum_steps_per_batch",
        "supported_api_revisions",
        "supported_database_revisions",
        "allowed_retry_modes",
        "allowed_execution_modes",
        "required_checksum_algorithm",
        "canonical_json_format",
        "replacement_preferences",
    ]
    .into_iter()
    .collect();
    let keys: HashSet<&str> = table.keys().map(String::as_str).collect();
    if keys.difference(&allowed).next().is_some() {
        return Err(FatalInputError::new("invalid release-profile structure"));
    }
    let mut replacement_preferences = HashMap::new();
    if let Some(prefs) = table.get("replacement_preferences") {
        let prefs_table = prefs
            .as_table()
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?;
        for (k, v) in prefs_table {
            replacement_preferences.insert(
                k.clone(),
                v.as_str()
                    .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?
                    .to_string(),
            );
        }
    }
    fn str_list(table: &toml::map::Map<String, toml::Value>, key: &str) -> Result<Vec<String>> {
        table
            .get(key)
            .and_then(|v| v.as_array())
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect()
            })
    }
    Ok(ReleaseProfile {
        release_profile_version: table
            .get("release_profile_version")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?
            .to_string(),
        maximum_runbooks_per_request: table
            .get("maximum_runbooks_per_request")
            .and_then(|v| v.as_integer())
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?,
        maximum_steps_per_batch: table
            .get("maximum_steps_per_batch")
            .and_then(|v| v.as_integer())
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?,
        supported_api_revisions: str_list(table, "supported_api_revisions")?,
        supported_database_revisions: str_list(table, "supported_database_revisions")?,
        allowed_retry_modes: str_list(table, "allowed_retry_modes")?,
        allowed_execution_modes: str_list(table, "allowed_execution_modes")?,
        required_checksum_algorithm: table
            .get("required_checksum_algorithm")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?
            .to_string(),
        canonical_json_format: table
            .get("canonical_json_format")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("invalid release-profile structure"))?
            .to_string(),
        replacement_preferences,
    })
}

pub fn load_api_contract(path: &Path) -> Result<HashMap<(String, String), ApiOperation>> {
    let text = fs::read_to_string(path)
        .map_err(|_| FatalInputError::new("invalid API contract structure"))?;
    let raw: JsonValue = serde_json::from_str(&text)
        .map_err(|_| FatalInputError::new("invalid API contract structure"))?;
    let obj = raw
        .as_object()
        .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?;
    if obj.len() != 2 || !obj.contains_key("profile_version") || !obj.contains_key("operations") {
        return Err(FatalInputError::new("invalid API contract structure"));
    }
    let mut ops = HashMap::new();
    let operations = obj
        .get("operations")
        .and_then(|v| v.as_array())
        .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?;
    for item in operations {
        let item_obj = item
            .as_object()
            .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?;
        let allowed: HashSet<&str> = [
            "operation_id",
            "api_revision",
            "path",
            "method",
            "accepted_request_content_types",
            "success_statuses",
            "idempotent",
            "required_capabilities",
        ]
        .into_iter()
        .collect();
        if item_obj.keys().any(|k| !allowed.contains(k.as_str())) {
            return Err(FatalInputError::new("unknown API contract field"));
        }
        let ctypes_raw = item_obj
            .get("accepted_request_content_types")
            .and_then(|v| v.as_array())
            .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?;
        let ctypes_str: Vec<String> = ctypes_raw
            .iter()
            .filter_map(|v| v.as_str().map(str::to_string))
            .collect();
        unique_array(&ctypes_str)?;
        let method_raw = item_obj
            .get("method")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?;
        let method = normalize_method(method_raw)
            .ok_or_else(|| FatalInputError::new("invalid method token"))?;
        let mut ctypes = Vec::new();
        for ct in ctypes_str {
            let n = normalize_content_type(&ct)
                .ok_or_else(|| FatalInputError::new("invalid media type with parameters"))?;
            ctypes.push(n);
        }
        let statuses: Vec<i64> = item_obj
            .get("success_statuses")
            .and_then(|v| v.as_array())
            .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?
            .iter()
            .filter_map(|v| v.as_i64())
            .collect();
        if statuses.is_empty() || statuses.iter().any(|s| *s < 200 || *s > 299) {
            return Err(FatalInputError::new("invalid success status"));
        }
        let mut sorted_statuses = statuses.clone();
        sorted_statuses.sort_unstable();
        let operation_id = item_obj
            .get("operation_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?
            .to_string();
        let api_revision = item_obj
            .get("api_revision")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?
            .to_string();
        let key = (api_revision.clone(), operation_id.clone());
        if ops.contains_key(&key) {
            return Err(FatalInputError::new("duplicate API operation identity"));
        }
        let required_caps: Vec<String> = item_obj
            .get("required_capabilities")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        ops.insert(
            key,
            ApiOperation {
                operation_id,
                api_revision,
                path: item_obj
                    .get("path")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?
                    .to_string(),
                method,
                accepted_request_content_types: ctypes,
                success_statuses: sorted_statuses,
                idempotent: item_obj
                    .get("idempotent")
                    .and_then(|v| v.as_bool())
                    .ok_or_else(|| FatalInputError::new("invalid API contract structure"))?,
                required_capabilities: sort_utf8(&required_caps),
            },
        );
    }
    Ok(ops)
}

pub fn load_deployments(db_path: &Path) -> Result<HashMap<String, Deployment>> {
    let conn = Connection::open_with_flags(db_path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    let mut tables = HashSet::new();
    let mut stmt = conn
        .prepare("SELECT name FROM sqlite_master WHERE type='table'")
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    for row in rows {
        tables.insert(row.map_err(|_| FatalInputError::new("unexpected SQLite schema"))?);
    }
    let required_tables: HashSet<String> = [
        "deployment_metadata",
        "database_capabilities",
        "applied_runbooks",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    if tables != required_tables {
        return Err(FatalInputError::new("unexpected SQLite schema"));
    }
    let mut deployments = HashMap::new();
    let mut stmt = conn
        .prepare("SELECT deployment_id, database_revision, capability_profile_version FROM deployment_metadata")
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    for row in rows {
        let (dep_id, db_rev, cap_ver) =
            row.map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
        deployments.insert(
            dep_id.clone(),
            Deployment {
                deployment_id: dep_id,
                database_revision: db_rev,
                capability_profile_version: cap_ver,
                capabilities: HashSet::new(),
                applied_runbooks: HashMap::new(),
            },
        );
    }
    let mut stmt = conn
        .prepare("SELECT deployment_id, capability_id FROM database_capabilities")
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    for row in rows {
        let (dep_id, cap) = row.map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
        let dep = deployments.get_mut(&dep_id).ok_or_else(|| {
            FatalInputError::new("foreign deployment reference in SQLite metadata")
        })?;
        dep.capabilities.insert(cap);
    }
    let mut stmt = conn
        .prepare("SELECT deployment_id, runbook_id, checksum_sha256 FROM applied_runbooks")
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
    for row in rows {
        let (dep_id, rb_id, checksum) =
            row.map_err(|_| FatalInputError::new("unexpected SQLite schema"))?;
        if !validate_checksum_syntax(&checksum) {
            return Err(FatalInputError::new("invalid stored checksum"));
        }
        let dep = deployments.get_mut(&dep_id).ok_or_else(|| {
            FatalInputError::new("foreign deployment reference in SQLite metadata")
        })?;
        dep.applied_runbooks.insert(rb_id, checksum);
    }
    Ok(deployments)
}

pub fn load_requests(path: &Path) -> Result<Vec<ReleaseRequest>> {
    let text = fs::read_to_string(path).map_err(|_| FatalInputError::new("malformed NDJSON"))?;
    let mut requests = Vec::new();
    let mut seen = HashSet::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            return Err(FatalInputError::new("malformed NDJSON"));
        }
        let raw: JsonValue =
            serde_json::from_str(line).map_err(|_| FatalInputError::new("malformed NDJSON"))?;
        let obj = raw
            .as_object()
            .ok_or_else(|| FatalInputError::new("malformed NDJSON"))?;
        let allowed: HashSet<&str> = [
            "request_id",
            "deployment_id",
            "target_runbook_ids",
            "target_api_revision",
            "target_database_revision",
        ]
        .into_iter()
        .collect();
        if obj.keys().any(|k| !allowed.contains(k.as_str())) {
            return Err(FatalInputError::new("malformed NDJSON"));
        }
        let target_runbook_ids: Vec<String> = obj
            .get("target_runbook_ids")
            .and_then(|v| v.as_array())
            .ok_or_else(|| FatalInputError::new("malformed NDJSON"))?
            .iter()
            .filter_map(|v| v.as_str().map(str::to_string))
            .collect();
        unique_array(&target_runbook_ids)?;
        let request_id = obj
            .get("request_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| FatalInputError::new("malformed NDJSON"))?
            .to_string();
        if !seen.insert(request_id.clone()) {
            return Err(FatalInputError::new("duplicate request ID"));
        }
        requests.push(ReleaseRequest {
            request_id,
            deployment_id: obj
                .get("deployment_id")
                .and_then(|v| v.as_str())
                .ok_or_else(|| FatalInputError::new("malformed NDJSON"))?
                .to_string(),
            target_runbook_ids,
            target_api_revision: obj
                .get("target_api_revision")
                .and_then(|v| v.as_str())
                .ok_or_else(|| FatalInputError::new("malformed NDJSON"))?
                .to_string(),
            target_database_revision: obj
                .get("target_database_revision")
                .and_then(|v| v.as_str())
                .ok_or_else(|| FatalInputError::new("malformed NDJSON"))?
                .to_string(),
        });
    }
    Ok(requests)
}

pub fn load_inputs(
    runbooks_dir: &Path,
    release_config: &Path,
    api_contract: &Path,
    database: &Path,
    requests_path: &Path,
) -> Result<PlannerInputs> {
    Ok(PlannerInputs {
        runbooks: load_runbooks(runbooks_dir)?,
        profile: load_profile(release_config)?,
        operations: load_api_contract(api_contract)?,
        deployments: load_deployments(database)?,
        requests: load_requests(requests_path)?,
    })
}
