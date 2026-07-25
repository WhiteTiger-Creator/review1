//! Full reconciliation engine mirroring the Python reference semantics.

use crate::canonical::{
    normalize_name, sha256_hex_serializable, sort_unique_components, sort_unique_strings,
};
use crate::error::{
    FatalError, CONFLICTING_DECLARATION_FLAGS, DUPLICATE_CONFIGURE_REQUEST_INDEX,
    DUPLICATE_DECLARATION_INDEX, DUPLICATE_FIND_REQUEST_INDEX, DUPLICATE_TARGET_PRODUCER,
    INVALID_INPUT_SCHEMA, TARGET_DEPENDENCY_CYCLE, UNKNOWN_REFERENCE,
    UNKNOWN_TARGET_REFERENCE,
};
use crate::loader::load_data_dir;
use crate::models::{
    ConfigureRequest, Declaration, DeclarationRow, FindRequest, LoadedData, LockObject,
    LockSectionRow, PackageCandidate, PackageSelectionRow, ProviderConfig, ProviderResponse,
    ProviderRow, RejectionRow, Report, RequestRow, SourceOverride, Summary, TargetRow,
};
use crate::version::{candidate_matches, source_version_matches, validate_version_or_null};
use serde::Serialize;
use std::collections::{HashMap, HashSet};
use std::path::Path;

const SECTION_ORDER: &[(&str, i64)] = &[
    ("declaration", 0),
    ("provider", 1),
    ("package_selection", 2),
    ("target_graph", 3),
    ("final_resolution", 4),
];

const SECTION_NAMES: &[&str] = &[
    "declaration",
    "provider",
    "package_selection",
    "target_graph",
    "final_resolution",
];

#[derive(Debug, Clone)]
struct Resolution {
    source_kind: String,
    identity_or_null: Option<String>,
    version_or_null: Option<String>,
    components: Vec<String>,
    produced_targets: Vec<String>,
    provider_response_id_or_null: Option<String>,
    provider_satisfies_or_null: Option<bool>,
    provider_intercepted: bool,
    provider_outcome: String,
    version_failed: bool,
    components_failed: bool,
}

impl Resolution {
    fn not_found(
        request: &FindRequest,
        components: Vec<String>,
        response_id_or_null: Option<String>,
        satisfies_or_null: Option<bool>,
        intercepted: bool,
        outcome: String,
        version_failed: bool,
        components_failed: bool,
    ) -> Self {
        Self {
            source_kind: "not_found".to_string(),
            identity_or_null: None,
            version_or_null: request.version_or_null.clone(),
            components,
            produced_targets: Vec::new(),
            provider_response_id_or_null: response_id_or_null,
            provider_satisfies_or_null: satisfies_or_null,
            provider_intercepted: intercepted,
            provider_outcome: outcome,
            version_failed,
            components_failed,
        }
    }
}

#[derive(Debug, Default)]
struct ConfigureState {
    configure_request_id: String,
    request_index: i64,
    project_id: String,
    provider_config_id: String,
    lock_mode: String,
    previous_lock: Option<LockObject>,
    find_requests: Vec<FindRequest>,
    resolutions: HashMap<String, Resolution>,
    rejections: Vec<RejectionRow>,
    provider_rows: Vec<ProviderRow>,
    package_selection_rows: Vec<PackageSelectionRow>,
    target_rows: Vec<TargetRow>,
    lock_section_rows: Vec<LockSectionRow>,
    action: String,
    resolved_dependency_count: i64,
    reused_section_count: i64,
    updated_section_count: i64,
    rejected: bool,
}

struct Indexes {
    declarations: Vec<Declaration>,
    find_by_id: HashMap<String, FindRequest>,
    providers: HashMap<String, ProviderConfig>,
    responses_by_key: HashMap<(String, String, String), Vec<ProviderResponse>>,
    candidates_by_name: HashMap<String, Vec<PackageCandidate>>,
    active_overrides: HashMap<String, SourceOverride>,
    targets: HashMap<String, crate::models::TargetNode>,
    edges: Vec<crate::models::TargetEdge>,
    locks: HashMap<String, LockObject>,
    configure_requests: Vec<ConfigureRequest>,
    ownership_by_project: HashMap<String, HashMap<String, Declaration>>,
    shadowed_ids: HashSet<String>,
}

pub fn reconcile(data_dir: &Path) -> Result<Report, FatalError> {
    let data = load_data_dir(data_dir)?;
    let indexes = build_indexes(&data)?;
    let mut configure_states = Vec::new();
    let mut project_ids = HashSet::new();

    for cfg in &indexes.configure_requests {
        project_ids.insert(cfg.project_id.clone());
        configure_states.push(process_configure_request(&indexes, cfg)?);
    }

    let mut provider_rows = Vec::new();
    let mut package_selection_rows = Vec::new();
    let mut target_rows = Vec::new();
    let mut lock_section_rows = Vec::new();
    let mut rejection_rows = Vec::new();

    for state in &configure_states {
        provider_rows.extend(state.provider_rows.clone());
        package_selection_rows.extend(state.package_selection_rows.clone());
        target_rows.extend(state.target_rows.clone());
        lock_section_rows.extend(state.lock_section_rows.clone());
        rejection_rows.extend(state.rejections.clone());
    }

    provider_rows.sort_by(|left, right| {
        (
            &left.configure_request_id,
            &left.find_request_id,
        )
            .cmp(&(&right.configure_request_id, &right.find_request_id))
    });
    package_selection_rows.sort_by(|left, right| {
        (
            &left.configure_request_id,
            &left.find_request_id,
        )
            .cmp(&(&right.configure_request_id, &right.find_request_id))
    });
    target_rows.sort_by(|left, right| {
        (
            &left.configure_request_id,
            &left.dependency_name,
            &left.target_id,
        )
            .cmp(&(
                &right.configure_request_id,
                &right.dependency_name,
                &right.target_id,
            ))
    });
    lock_section_rows.sort_by(|left, right| {
        let left_order = section_order(&left.section);
        let right_order = section_order(&right.section);
        (
            &left.configure_request_id,
            &left.dependency_name,
            left_order,
        )
            .cmp(&(
                &right.configure_request_id,
                &right.dependency_name,
                right_order,
            ))
    });
    rejection_rows.sort_by(|left, right| {
        (
            &left.configure_request_id,
            left.find_request_id_or_null.as_deref().unwrap_or(""),
            &left.reason_token,
        )
            .cmp(&(
                &right.configure_request_id,
                right.find_request_id_or_null.as_deref().unwrap_or(""),
                &right.reason_token,
            ))
    });

    let declaration_rows = build_declaration_rows(&indexes, &project_ids);
    let declaration_owner_count = declaration_rows
        .iter()
        .filter(|row| row.ownership == "owner")
        .count() as i64;

    let request_rows = configure_states
        .iter()
        .map(|state| RequestRow {
            configure_request_id: state.configure_request_id.clone(),
            request_index: state.request_index,
            project_id: state.project_id.clone(),
            provider_config_id: state.provider_config_id.clone(),
            lock_mode: state.lock_mode.clone(),
            action: state.action.clone(),
            resolved_dependency_count: state.resolved_dependency_count,
            reused_section_count: state.reused_section_count,
            updated_section_count: state.updated_section_count,
        })
        .collect();

    let summary = Summary {
        configure_request_count: configure_states.len() as i64,
        reuse_count: configure_states
            .iter()
            .filter(|state| state.action == "reuse_resolution")
            .count() as i64,
        update_count: configure_states
            .iter()
            .filter(|state| state.action == "update_resolution")
            .count() as i64,
        reject_count: configure_states
            .iter()
            .filter(|state| state.action == "reject_configuration")
            .count() as i64,
        declaration_owner_count,
        target_row_count: target_rows.len() as i64,
    };

    Ok(Report {
        schema_version: 1,
        request_rows,
        declaration_rows,
        provider_rows,
        package_selection_rows,
        target_rows,
        lock_section_rows,
        rejection_rows,
        summary,
    })
}

fn section_order(section: &str) -> i64 {
    SECTION_ORDER
        .iter()
        .find_map(|(name, order)| (*name == section).then_some(*order))
        .unwrap_or(99)
}

fn build_indexes(data: &LoadedData) -> Result<Indexes, FatalError> {
    let providers: HashMap<String, ProviderConfig> = data
        .providers
        .iter()
        .map(|provider| (provider.provider_config_id.clone(), provider.clone()))
        .collect();
    let locks: HashMap<String, LockObject> = data
        .locks
        .iter()
        .map(|lock| (lock.lock_id.clone(), lock.clone()))
        .collect();
    let find_by_id: HashMap<String, FindRequest> = data
        .find_requests
        .iter()
        .map(|row| (row.find_request_id.clone(), row.clone()))
        .collect();

    for decl in &data.declarations {
        validate_version_or_null(decl.declared_version_or_null.as_deref())?;
        validate_version_or_null(decl.find_package_args.version_or_null.as_deref())?;
    }
    for row in &data.find_requests {
        validate_version_or_null(row.version_or_null.as_deref())?;
    }
    for override_row in &data.overrides {
        validate_version_or_null(override_row.version_or_null.as_deref())?;
    }
    for response in &data.provider_responses {
        validate_version_or_null(response.version_or_null.as_deref())?;
    }
    for candidate in &data.candidates {
        validate_version_or_null(Some(candidate.version.as_str()))?;
    }

    let mut seen_cfg_index = HashSet::new();
    for cfg in &data.policy.configure_requests {
        if !seen_cfg_index.insert(cfg.request_index) {
            return Err(FatalError::new(
                DUPLICATE_CONFIGURE_REQUEST_INDEX,
                cfg.request_index.to_string(),
            ));
        }
        if !providers.contains_key(&cfg.provider_config_id) {
            return Err(FatalError::new(
                UNKNOWN_REFERENCE,
                cfg.provider_config_id.clone(),
            ));
        }
        if let Some(lock_id) = &cfg.previous_lock_id_or_null {
            if !locks.contains_key(lock_id) {
                return Err(FatalError::new(UNKNOWN_REFERENCE, lock_id.clone()));
            }
        }
        for find_id in &cfg.find_request_ids {
            if !find_by_id.contains_key(find_id) {
                return Err(FatalError::new(UNKNOWN_REFERENCE, find_id.clone()));
            }
        }
    }

    let mut declarations_by_project: HashMap<String, Vec<Declaration>> = HashMap::new();
    for decl in &data.declarations {
        declarations_by_project
            .entry(decl.project_id.clone())
            .or_default()
            .push(decl.clone());
    }

    let mut ownership_by_project: HashMap<String, HashMap<String, Declaration>> = HashMap::new();
    let mut shadowed_ids = HashSet::new();
    for (project_id, mut decls) in declarations_by_project {
        decls.sort_by(|left, right| {
            (
                left.declaration_index,
                left.declaration_id.as_str(),
            )
                .cmp(&(right.declaration_index, right.declaration_id.as_str()))
        });
        let mut seen_index = HashSet::new();
        let mut owners: HashMap<String, Declaration> = HashMap::new();
        for decl in decls {
            if !seen_index.insert(decl.declaration_index) {
                return Err(FatalError::new(
                    DUPLICATE_DECLARATION_INDEX,
                    decl.declaration_index.to_string(),
                ));
            }
            let norm = normalize_name(&decl.dependency_name);
            if owners.contains_key(&norm) {
                shadowed_ids.insert(decl.declaration_id.clone());
            } else {
                owners.insert(norm.clone(), decl.clone());
                let owner = owners.get(&norm).unwrap();
                if owner.override_find_package && owner.find_package_args.enabled {
                    return Err(FatalError::new(
                        CONFLICTING_DECLARATION_FLAGS,
                        owner.declaration_id.clone(),
                    ));
                }
            }
        }
        ownership_by_project.insert(project_id, owners);
    }

    let mut find_by_project: HashMap<String, Vec<&FindRequest>> = HashMap::new();
    for row in &data.find_requests {
        find_by_project
            .entry(row.project_id.clone())
            .or_default()
            .push(row);
    }
    for rows in find_by_project.values() {
        let mut seen_index = HashSet::new();
        for row in rows {
            if !seen_index.insert(row.request_index) {
                return Err(FatalError::new(
                    DUPLICATE_FIND_REQUEST_INDEX,
                    row.request_index.to_string(),
                ));
            }
        }
    }

    let mut active_overrides: HashMap<String, SourceOverride> = HashMap::new();
    for override_row in &data.overrides {
        if !override_row.active {
            continue;
        }
        let norm = normalize_name(&override_row.dependency_name);
        if active_overrides.contains_key(&norm) {
            return Err(FatalError::new(INVALID_INPUT_SCHEMA, norm));
        }
        active_overrides.insert(norm, override_row.clone());
    }

    let mut responses_by_key: HashMap<(String, String, String), Vec<ProviderResponse>> =
        HashMap::new();
    for response in &data.provider_responses {
        let key = (
            response.provider_config_id.clone(),
            normalize_name(&response.dependency_name),
            response.request_kind.clone(),
        );
        responses_by_key
            .entry(key)
            .or_default()
            .push(response.clone());
    }
    for items in responses_by_key.values_mut() {
        items.sort_by(|left, right| left.response_id.cmp(&right.response_id));
    }

    let mut candidates_by_name: HashMap<String, Vec<PackageCandidate>> = HashMap::new();
    for candidate in &data.candidates {
        let norm = normalize_name(&candidate.dependency_name);
        candidates_by_name
            .entry(norm)
            .or_default()
            .push(candidate.clone());
    }
    for items in candidates_by_name.values_mut() {
        items.sort_by(|left, right| left.candidate_id.cmp(&right.candidate_id));
    }

    let targets: HashMap<String, crate::models::TargetNode> = data
        .target_graph
        .targets
        .iter()
        .map(|target| (target.target_id.clone(), target.clone()))
        .collect();

    let mut configure_requests = data.policy.configure_requests.clone();
    configure_requests.sort_by_key(|cfg| cfg.request_index);

    Ok(Indexes {
        declarations: data.declarations.clone(),
        find_by_id,
        providers,
        responses_by_key,
        candidates_by_name,
        active_overrides,
        targets,
        edges: data.target_graph.edges.clone(),
        locks,
        configure_requests,
        ownership_by_project,
        shadowed_ids,
    })
}

fn pick_provider_response(
    indexes: &Indexes,
    provider_config_id: &str,
    dependency_name: &str,
    request_kind: &str,
) -> Option<ProviderResponse> {
    let key = (
        provider_config_id.to_string(),
        normalize_name(dependency_name),
        request_kind.to_string(),
    );
    indexes
        .responses_by_key
        .get(&key)
        .and_then(|items| items.first().cloned())
}

fn components_satisfied(required: &[String], provided: &[String]) -> bool {
    let provided_set: HashSet<&str> = provided.iter().map(String::as_str).collect();
    required
        .iter()
        .all(|component| provided_set.contains(component.as_str()))
}

fn pick_package_candidate(
    indexes: &Indexes,
    dependency_name: &str,
    request: &FindRequest,
) -> Result<Option<PackageCandidate>, FatalError> {
    let norm = normalize_name(dependency_name);
    let components = sort_unique_components(&request.components);
    let items = indexes.candidates_by_name.get(&norm);
    let Some(items) = items else {
        return Ok(None);
    };
    for candidate in items {
        if !candidate_matches(
            &candidate.version,
            &candidate.compatibility,
            request.version_or_null.as_deref(),
            request.exact,
        )? {
            continue;
        }
        if !components_satisfied(&components, &candidate.provided_components) {
            continue;
        }
        return Ok(Some(candidate.clone()));
    }
    Ok(None)
}

fn fetchcontent_components_ok(request_components: &[String]) -> bool {
    if request_components.is_empty() {
        return true;
    }
    request_components.iter().all(|component| component == "default")
}

fn resolve_find_package(
    indexes: &Indexes,
    project_id: &str,
    request: &FindRequest,
    provider_config: &ProviderConfig,
) -> Result<Resolution, FatalError> {
    let norm = normalize_name(&request.dependency_name);
    let owner = indexes
        .ownership_by_project
        .get(project_id)
        .and_then(|owners| owners.get(&norm));
    let components = sort_unique_components(&request.components);
    let bypass = request.bypass_provider;
    let override_row = indexes.active_overrides.get(&norm);

    let mut version_failed = false;
    let mut components_failed = false;

    if let Some(override_row) = override_row {
        if !source_version_matches(
            override_row.version_or_null.as_deref(),
            request.version_or_null.as_deref(),
            request.exact,
        )? {
            version_failed = true;
        } else if !components_satisfied(&components, &override_row.provided_components) {
            components_failed = true;
        } else {
            return Ok(Resolution {
                source_kind: "override".to_string(),
                identity_or_null: Some(override_row.override_id.clone()),
                version_or_null: override_row.version_or_null.clone(),
                components,
                produced_targets: override_row.produced_targets.clone(),
                provider_response_id_or_null: None,
                provider_satisfies_or_null: None,
                provider_intercepted: false,
                provider_outcome: "provider_skipped".to_string(),
                version_failed: false,
                components_failed: false,
            });
        }
    }

    let mut intercepted = false;
    let mut outcome = "provider_skipped".to_string();
    let mut response_id_or_null = None;
    let mut satisfies_or_null = None;

    let intercept = !bypass && provider_config.intercept_find_package;
    if intercept {
        intercepted = true;
        let response = pick_provider_response(
            indexes,
            &provider_config.provider_config_id,
            &request.dependency_name,
            "find_package",
        );
        match response {
            None => outcome = "no_response".to_string(),
            Some(response) if !response.satisfies => {
                outcome = "provider_declined".to_string();
                response_id_or_null = Some(response.response_id.clone());
                satisfies_or_null = Some(false);
            }
            Some(response) => {
                response_id_or_null = Some(response.response_id.clone());
                satisfies_or_null = Some(true);
                if !source_version_matches(
                    response.version_or_null.as_deref(),
                    request.version_or_null.as_deref(),
                    request.exact,
                )? {
                    version_failed = true;
                    outcome = "provider_declined".to_string();
                } else if !components_satisfied(&components, &response.provided_components) {
                    components_failed = true;
                    outcome = "provider_declined".to_string();
                } else {
                    outcome = "provider_resolved".to_string();
                    return Ok(Resolution {
                        source_kind: "provider".to_string(),
                        identity_or_null: Some(response.response_id.clone()),
                        version_or_null: response.version_or_null.clone(),
                        components,
                        produced_targets: response.produced_targets.clone(),
                        provider_response_id_or_null: Some(response.response_id.clone()),
                        provider_satisfies_or_null: Some(true),
                        provider_intercepted: true,
                        provider_outcome: outcome,
                        version_failed: false,
                        components_failed: false,
                    });
                }
            }
        }
    }

    if let Some(owner) = owner {
        if owner.override_find_package {
            if !source_version_matches(
                owner.declared_version_or_null.as_deref(),
                request.version_or_null.as_deref(),
                request.exact,
            )? {
                version_failed = true;
            } else if !fetchcontent_components_ok(&components) {
                components_failed = true;
            } else {
                return Ok(Resolution {
                    source_kind: "fetchcontent".to_string(),
                    identity_or_null: Some(owner.declaration_id.clone()),
                    version_or_null: owner.declared_version_or_null.clone(),
                    components: if components.is_empty() {
                        vec!["default".to_string()]
                    } else {
                        components
                    },
                    produced_targets: owner.produced_targets.clone(),
                    provider_response_id_or_null: response_id_or_null,
                    provider_satisfies_or_null: satisfies_or_null,
                    provider_intercepted: intercepted,
                    provider_outcome: outcome,
                    version_failed: false,
                    components_failed: false,
                });
            }
        } else if let Some(candidate) =
            pick_package_candidate(indexes, &request.dependency_name, request)?
        {
            return Ok(Resolution {
                source_kind: "package".to_string(),
                identity_or_null: Some(candidate.candidate_id.clone()),
                version_or_null: Some(candidate.version.clone()),
                components,
                produced_targets: candidate.produced_targets.clone(),
                provider_response_id_or_null: response_id_or_null,
                provider_satisfies_or_null: satisfies_or_null,
                provider_intercepted: intercepted,
                provider_outcome: outcome,
                version_failed: false,
                components_failed: false,
            });
        } else if !source_version_matches(
            owner.declared_version_or_null.as_deref(),
            request.version_or_null.as_deref(),
            request.exact,
        )? {
            version_failed = true;
        } else if !fetchcontent_components_ok(&components) {
            components_failed = true;
        } else {
            return Ok(Resolution {
                source_kind: "fetchcontent".to_string(),
                identity_or_null: Some(owner.declaration_id.clone()),
                version_or_null: owner.declared_version_or_null.clone(),
                components: if components.is_empty() {
                    vec!["default".to_string()]
                } else {
                    components
                },
                produced_targets: owner.produced_targets.clone(),
                provider_response_id_or_null: response_id_or_null,
                provider_satisfies_or_null: satisfies_or_null,
                provider_intercepted: intercepted,
                provider_outcome: outcome,
                version_failed: false,
                components_failed: false,
            });
        }
    } else if let Some(candidate) =
        pick_package_candidate(indexes, &request.dependency_name, request)?
    {
        return Ok(Resolution {
            source_kind: "package".to_string(),
            identity_or_null: Some(candidate.candidate_id.clone()),
            version_or_null: Some(candidate.version.clone()),
            components,
            produced_targets: candidate.produced_targets.clone(),
            provider_response_id_or_null: response_id_or_null,
            provider_satisfies_or_null: satisfies_or_null,
            provider_intercepted: intercepted,
            provider_outcome: outcome,
            version_failed: false,
            components_failed: false,
        });
    }

    Ok(Resolution::not_found(
        request,
        components,
        response_id_or_null,
        satisfies_or_null,
        intercepted,
        outcome,
        version_failed,
        components_failed,
    ))
}

fn resolve_make_available(
    indexes: &Indexes,
    project_id: &str,
    request: &FindRequest,
    provider_config: &ProviderConfig,
) -> Result<Resolution, FatalError> {
    let norm = normalize_name(&request.dependency_name);
    let owner = indexes
        .ownership_by_project
        .get(project_id)
        .and_then(|owners| owners.get(&norm));
    let components = sort_unique_components(&request.components);
    let bypass = request.bypass_provider;
    let override_row = indexes.active_overrides.get(&norm);

    let mut version_failed = false;
    let mut components_failed = false;

    if let Some(override_row) = override_row {
        if !source_version_matches(
            override_row.version_or_null.as_deref(),
            request.version_or_null.as_deref(),
            request.exact,
        )? {
            version_failed = true;
        } else if !components_satisfied(&components, &override_row.provided_components) {
            components_failed = true;
        } else {
            return Ok(Resolution {
                source_kind: "override".to_string(),
                identity_or_null: Some(override_row.override_id.clone()),
                version_or_null: override_row.version_or_null.clone(),
                components,
                produced_targets: override_row.produced_targets.clone(),
                provider_response_id_or_null: None,
                provider_satisfies_or_null: None,
                provider_intercepted: false,
                provider_outcome: "provider_skipped".to_string(),
                version_failed: false,
                components_failed: false,
            });
        }
    }

    let mut intercepted = false;
    let mut outcome = "provider_skipped".to_string();
    let mut response_id_or_null = None;
    let mut satisfies_or_null = None;

    let intercept = !bypass && provider_config.intercept_fetchcontent;
    if intercept {
        intercepted = true;
        let response = pick_provider_response(
            indexes,
            &provider_config.provider_config_id,
            &request.dependency_name,
            "make_available",
        );
        match response {
            None => outcome = "no_response".to_string(),
            Some(response) if !response.satisfies => {
                outcome = "provider_declined".to_string();
                response_id_or_null = Some(response.response_id.clone());
                satisfies_or_null = Some(false);
            }
            Some(response) => {
                response_id_or_null = Some(response.response_id.clone());
                satisfies_or_null = Some(true);
                if !source_version_matches(
                    response.version_or_null.as_deref(),
                    request.version_or_null.as_deref(),
                    request.exact,
                )? {
                    version_failed = true;
                    outcome = "provider_declined".to_string();
                } else if !components_satisfied(&components, &response.provided_components) {
                    components_failed = true;
                    outcome = "provider_declined".to_string();
                } else {
                    outcome = "provider_resolved".to_string();
                    return Ok(Resolution {
                        source_kind: "provider".to_string(),
                        identity_or_null: Some(response.response_id.clone()),
                        version_or_null: response.version_or_null.clone(),
                        components,
                        produced_targets: response.produced_targets.clone(),
                        provider_response_id_or_null: Some(response.response_id.clone()),
                        provider_satisfies_or_null: Some(true),
                        provider_intercepted: true,
                        provider_outcome: outcome,
                        version_failed: false,
                        components_failed: false,
                    });
                }
            }
        }
    }

    if let Some(owner) = owner {
        let fpa = &owner.find_package_args;
        if fpa.enabled && fpa.try_system_first {
            if let Some(candidate) =
                pick_package_candidate(indexes, &request.dependency_name, request)?
            {
                return Ok(Resolution {
                    source_kind: "package".to_string(),
                    identity_or_null: Some(candidate.candidate_id.clone()),
                    version_or_null: Some(candidate.version.clone()),
                    components,
                    produced_targets: candidate.produced_targets.clone(),
                    provider_response_id_or_null: response_id_or_null,
                    provider_satisfies_or_null: satisfies_or_null,
                    provider_intercepted: intercepted,
                    provider_outcome: outcome,
                    version_failed: false,
                    components_failed: false,
                });
            }
        }

        let decl_components = if fpa.enabled {
            sort_unique_components(&fpa.components)
        } else {
            components.clone()
        };
        let decl_version = if fpa.enabled {
            fpa.version_or_null.clone()
        } else {
            owner.declared_version_or_null.clone()
        };
        if !source_version_matches(
            decl_version.as_deref(),
            request.version_or_null.as_deref(),
            request.exact,
        )? {
            version_failed = true;
        } else if !fetchcontent_components_ok(if fpa.enabled {
            &decl_components
        } else {
            &components
        }) {
            components_failed = true;
        } else if fpa.enabled
            && !components.is_empty()
            && !components_satisfied(&components, &decl_components)
        {
            components_failed = true;
        } else {
            let report_components = if fpa.enabled {
                decl_components
            } else if components.is_empty() {
                vec!["default".to_string()]
            } else {
                components
            };
            return Ok(Resolution {
                source_kind: "fetchcontent".to_string(),
                identity_or_null: Some(owner.declaration_id.clone()),
                version_or_null: decl_version,
                components: report_components,
                produced_targets: owner.produced_targets.clone(),
                provider_response_id_or_null: response_id_or_null,
                provider_satisfies_or_null: satisfies_or_null,
                provider_intercepted: intercepted,
                provider_outcome: outcome,
                version_failed: false,
                components_failed: false,
            });
        }
    }

    Ok(Resolution::not_found(
        request,
        components,
        response_id_or_null,
        satisfies_or_null,
        intercepted,
        outcome,
        version_failed,
        components_failed,
    ))
}

fn resolve_request(
    indexes: &Indexes,
    project_id: &str,
    request: &FindRequest,
    provider_config: &ProviderConfig,
) -> Result<Resolution, FatalError> {
    if request.request_kind == "find_package" {
        resolve_find_package(indexes, project_id, request, provider_config)
    } else {
        resolve_make_available(indexes, project_id, request, provider_config)
    }
}

fn compute_closure(
    indexes: &Indexes,
    root_targets: &[String],
) -> Result<(Vec<String>, Vec<Vec<String>>), FatalError> {
    for target_id in root_targets {
        if !indexes.targets.contains_key(target_id) {
            return Err(FatalError::new(UNKNOWN_TARGET_REFERENCE, target_id.clone()));
        }
    }

    let mut closure: HashSet<String> = root_targets.iter().cloned().collect();
    let mut changed = true;
    while changed {
        changed = false;
        for edge in &indexes.edges {
            if closure.contains(&edge.from_target) {
                if !indexes.targets.contains_key(&edge.to_target) {
                    return Err(FatalError::new(
                        UNKNOWN_TARGET_REFERENCE,
                        edge.to_target.clone(),
                    ));
                }
                if closure.insert(edge.to_target.clone()) {
                    changed = true;
                }
            }
        }
    }

    let mut closure_edges = Vec::new();
    for edge in &indexes.edges {
        if closure.contains(&edge.from_target) && closure.contains(&edge.to_target) {
            closure_edges.push(vec![edge.from_target.clone(), edge.to_target.clone()]);
        }
    }
    closure_edges.sort_by(|left, right| (left[0].as_str(), left[1].as_str()).cmp(&(right[0].as_str(), right[1].as_str())));
    Ok((sort_unique_strings(&closure.into_iter().collect::<Vec<_>>()), closure_edges))
}

fn has_cycle(nodes: &HashSet<String>, edges: &[crate::models::TargetEdge]) -> bool {
    let mut adjacency: HashMap<&str, Vec<&str>> = HashMap::new();
    for node in nodes {
        adjacency.insert(node.as_str(), Vec::new());
    }
    for edge in edges {
        if nodes.contains(&edge.from_target) && nodes.contains(&edge.to_target) {
            adjacency
                .entry(edge.from_target.as_str())
                .or_default()
                .push(edge.to_target.as_str());
        }
    }

    fn dfs<'a>(
        node: &'a str,
        adjacency: &HashMap<&'a str, Vec<&'a str>>,
        visiting: &mut HashSet<&'a str>,
        visited: &mut HashSet<&'a str>,
    ) -> bool {
        if visiting.contains(node) {
            return true;
        }
        if visited.contains(node) {
            return false;
        }
        visiting.insert(node);
        for neighbor in adjacency.get(node).into_iter().flatten() {
            if dfs(neighbor, adjacency, visiting, visited) {
                return true;
            }
        }
        visiting.remove(node);
        visited.insert(node);
        false
    }

    for node in nodes {
        let mut visiting = HashSet::new();
        let mut visited = HashSet::new();
        if dfs(node.as_str(), &adjacency, &mut visiting, &mut visited) {
            return true;
        }
    }
    false
}

#[derive(Serialize)]
struct DeclarationPreimage<'a> {
    content_digest: &'a str,
    declaration_id: &'a str,
    declared_version_or_null: Option<&'a str>,
    dependency_name: String,
    find_package_args: &'a crate::models::FindPackageArgs,
    override_find_package: bool,
    produced_targets: Vec<String>,
    source_identity: &'a str,
    source_kind: &'a str,
}

#[derive(Serialize)]
struct ProviderPreimage {
    bypass_provider: bool,
    dependency_name: String,
    provider_config_id: String,
    request_kind: String,
    response_content_digest_or_null: Option<String>,
    response_id_or_null: Option<String>,
    satisfies_or_null: Option<bool>,
}

#[derive(Serialize)]
struct PackageSelectionPreimage {
    candidate_id_or_null: Option<String>,
    components: Vec<String>,
    dependency_name: String,
    exact: bool,
    source_kind: String,
    version_or_null: Option<String>,
}

#[derive(Serialize)]
struct TargetGraphPreimage {
    closure_targets: Vec<String>,
    dependency_name: String,
    edges: Vec<Vec<String>>,
    root_targets: Vec<String>,
}

#[derive(Serialize)]
struct FinalResolutionPreimage {
    dependency_name: String,
    declaration_result_digest: String,
    package_selection_result_digest: String,
    provider_result_digest: String,
    target_graph_result_digest: String,
}

#[derive(Serialize)]
struct StoredDeclaration<'a> {
    declaration_id: &'a str,
    ownership: &'static str,
}

#[derive(Serialize)]
struct StoredProvider {
    response_id_or_null: Option<String>,
    source_kind: &'static str,
}

#[derive(Serialize)]
struct StoredPackageSelection {
    source_kind: String,
    identity: Option<String>,
}

#[derive(Serialize)]
struct StoredTargetGraph {
    closure_targets: Vec<String>,
}

#[derive(Serialize)]
struct StoredFinalResolution {
    action_hint: &'static str,
    source_kind: String,
}

fn digest_of<T: Serialize>(value: &T) -> Result<String, FatalError> {
    sha256_hex_serializable(value)
        .map_err(|err| FatalError::new(crate::error::OUTPUT_WRITE_FAILED, err.to_string()))
}

fn rejection_reason(resolution: &Resolution) -> &'static str {
    if resolution.components_failed {
        "components_unsatisfied"
    } else if resolution.version_failed {
        "version_mismatch"
    } else {
        "unresolved_dependency"
    }
}

fn process_configure_request(
    indexes: &Indexes,
    cfg: &ConfigureRequest,
) -> Result<ConfigureState, FatalError> {
    let provider_config = indexes
        .providers
        .get(&cfg.provider_config_id)
        .expect("validated provider");
    let previous_lock = cfg
        .previous_lock_id_or_null
        .as_ref()
        .and_then(|lock_id| indexes.locks.get(lock_id).cloned());
    let find_requests: Vec<FindRequest> = cfg
        .find_request_ids
        .iter()
        .map(|find_id| indexes.find_by_id.get(find_id).cloned().expect("validated find id"))
        .collect();

    let mut state = ConfigureState {
        configure_request_id: cfg.configure_request_id.clone(),
        request_index: cfg.request_index,
        project_id: cfg.project_id.clone(),
        provider_config_id: cfg.provider_config_id.clone(),
        lock_mode: cfg.lock_mode.clone(),
        previous_lock: previous_lock.clone(),
        find_requests: find_requests.clone(),
        resolutions: HashMap::new(),
        rejections: Vec::new(),
        provider_rows: Vec::new(),
        package_selection_rows: Vec::new(),
        target_rows: Vec::new(),
        lock_section_rows: Vec::new(),
        action: "reuse_resolution".to_string(),
        resolved_dependency_count: 0,
        reused_section_count: 0,
        updated_section_count: 0,
        rejected: false,
    };

    let mut producer_map: HashMap<String, String> = HashMap::new();
    let mut all_closure_nodes = HashSet::new();

    for request in &state.find_requests.clone() {
        let resolution = resolve_request(indexes, &cfg.project_id, request, provider_config)?;
        let norm = normalize_name(&request.dependency_name);
        state.resolutions.insert(norm.clone(), resolution.clone());

        state.provider_rows.push(ProviderRow {
            configure_request_id: cfg.configure_request_id.clone(),
            find_request_id: request.find_request_id.clone(),
            dependency_name: norm.clone(),
            intercepted: resolution.provider_intercepted,
            bypass_provider: request.bypass_provider,
            response_id_or_null: resolution.provider_response_id_or_null.clone(),
            satisfies_or_null: resolution.provider_satisfies_or_null,
            outcome: resolution.provider_outcome.clone(),
        });

        let report_components = sort_unique_components(&resolution.components);
        state.package_selection_rows.push(PackageSelectionRow {
            configure_request_id: cfg.configure_request_id.clone(),
            find_request_id: request.find_request_id.clone(),
            dependency_name: norm.clone(),
            source_kind: resolution.source_kind.clone(),
            identity_or_null: resolution.identity_or_null.clone(),
            version_or_null: resolution.version_or_null.clone(),
            components: report_components,
        });

        let (closure_targets, closure_edges) = if resolution.source_kind == "not_found" {
            if request.required {
                let reason = rejection_reason(&resolution);
                state.rejections.push(RejectionRow {
                    configure_request_id: cfg.configure_request_id.clone(),
                    find_request_id_or_null: Some(request.find_request_id.clone()),
                    reason_token: reason.to_string(),
                    message: format!("{reason} for {norm}"),
                });
                state.rejected = true;
            }
            (Vec::new(), Vec::new())
        } else {
            state.resolved_dependency_count += 1;
            for target_id in &resolution.produced_targets {
                if let Some(existing) = producer_map.get(target_id) {
                    if existing != &norm {
                        return Err(FatalError::new(
                            DUPLICATE_TARGET_PRODUCER,
                            target_id.clone(),
                        ));
                    }
                }
                producer_map.insert(target_id.clone(), norm.clone());
            }

            let (closure_targets, closure_edges) =
                compute_closure(indexes, &resolution.produced_targets)?;
            all_closure_nodes.extend(closure_targets.iter().cloned());

            for target_id in &closure_targets {
                let role = if resolution.produced_targets.iter().any(|root| root == target_id) {
                    "root"
                } else {
                    "transitive"
                };
                let producer = indexes
                    .targets
                    .get(target_id)
                    .map(|target| target.producer_dependency.clone())
                    .unwrap_or_default();
                state.target_rows.push(TargetRow {
                    configure_request_id: cfg.configure_request_id.clone(),
                    dependency_name: norm.clone(),
                    target_id: target_id.clone(),
                    role: role.to_string(),
                    producer_dependency: producer,
                });
            }
            (closure_targets, closure_edges)
        };

        let owner = indexes
            .ownership_by_project
            .get(&cfg.project_id)
            .and_then(|owners| owners.get(&norm));
        let prior_sections = state
            .previous_lock
            .as_ref()
            .and_then(|lock| lock.sections_by_dependency.get(&norm));

        let (decl_digest_in, decl_digest_out) = if let Some(owner) = owner {
            let decl_input = DeclarationPreimage {
                content_digest: &owner.content_digest,
                declaration_id: &owner.declaration_id,
                declared_version_or_null: owner.declared_version_or_null.as_deref(),
                dependency_name: norm.clone(),
                find_package_args: &owner.find_package_args,
                override_find_package: owner.override_find_package,
                produced_targets: sort_unique_strings(&owner.produced_targets),
                source_identity: &owner.source_identity,
                source_kind: &owner.source_kind,
            };
            let decl_result = StoredDeclaration {
                declaration_id: &owner.declaration_id,
                ownership: "owner",
            };
            (Some(digest_of(&decl_input)?), Some(digest_of(&decl_result)?))
        } else {
            (None, None)
        };

        let provider_skipped = indexes.active_overrides.contains_key(&norm)
            || request.bypass_provider
            || (request.request_kind == "find_package"
                && !provider_config.intercept_find_package)
            || (request.request_kind == "make_available"
                && !provider_config.intercept_fetchcontent);
        let provider_response = if provider_skipped {
            None
        } else {
            pick_provider_response(
                indexes,
                &provider_config.provider_config_id,
                &request.dependency_name,
                &request.request_kind,
            )
        };
        let prov_input = ProviderPreimage {
            bypass_provider: request.bypass_provider,
            dependency_name: norm.clone(),
            provider_config_id: provider_config.provider_config_id.clone(),
            request_kind: request.request_kind.clone(),
            response_content_digest_or_null: provider_response
                .as_ref()
                .map(|response| response.content_digest.clone()),
            response_id_or_null: provider_response
                .as_ref()
                .map(|response| response.response_id.clone()),
            satisfies_or_null: provider_response.as_ref().map(|response| response.satisfies),
        };
        let prov_result = if resolution.source_kind == "provider" {
            StoredProvider {
                response_id_or_null: resolution.identity_or_null.clone(),
                source_kind: "provider",
            }
        } else {
            StoredProvider {
                response_id_or_null: None,
                source_kind: "skipped",
            }
        };
        let prov_digest_in = digest_of(&prov_input)?;
        let prov_digest_out = digest_of(&prov_result)?;

        let candidate_id_or_null = match resolution.source_kind.as_str() {
            "package" | "provider" | "fetchcontent" | "override" => resolution.identity_or_null.clone(),
            _ => None,
        };
        let pkg_input = PackageSelectionPreimage {
            candidate_id_or_null: if resolution.source_kind == "package" {
                resolution.identity_or_null.clone()
            } else {
                None
            },
            components: sort_unique_components(&resolution.components),
            dependency_name: norm.clone(),
            exact: request.exact,
            source_kind: resolution.source_kind.clone(),
            version_or_null: resolution.version_or_null.clone(),
        };
        let pkg_result = StoredPackageSelection {
            source_kind: resolution.source_kind.clone(),
            identity: candidate_id_or_null,
        };
        let pkg_digest_in = digest_of(&pkg_input)?;
        let pkg_digest_out = digest_of(&pkg_result)?;

        let tg_input = TargetGraphPreimage {
            closure_targets: sort_unique_strings(&closure_targets),
            dependency_name: norm.clone(),
            edges: closure_edges.clone(),
            root_targets: sort_unique_strings(&resolution.produced_targets),
        };
        let tg_result = StoredTargetGraph {
            closure_targets: sort_unique_strings(&closure_targets),
        };
        let tg_digest_in = digest_of(&tg_input)?;
        let tg_digest_out = digest_of(&tg_result)?;

        let mut section_results: HashMap<String, (String, String)> = HashMap::new();
        let mut stale_sections = HashSet::new();

        let section_specs = vec![
            ("declaration", decl_digest_in.clone(), decl_digest_out.clone(), owner.is_some()),
            (
                "provider",
                Some(prov_digest_in.clone()),
                Some(prov_digest_out.clone()),
                true,
            ),
            (
                "package_selection",
                Some(pkg_digest_in.clone()),
                Some(pkg_digest_out.clone()),
                true,
            ),
            (
                "target_graph",
                Some(tg_digest_in.clone()),
                Some(tg_digest_out.clone()),
                true,
            ),
        ];

        for (section_name, input_digest, result_digest, applicable) in section_specs {
            if !applicable {
                stale_sections.insert(section_name.to_string());
                continue;
            }
            let (Some(input_digest), Some(result_digest)) = (input_digest, result_digest) else {
                stale_sections.insert(section_name.to_string());
                continue;
            };
            let prior = prior_sections.and_then(|sections| sections.get(section_name));
            if prior.is_none()
                || prior.unwrap().input_digest != input_digest
                || prior.unwrap().result_digest != result_digest
            {
                stale_sections.insert(section_name.to_string());
            }
            section_results.insert(section_name.to_string(), (input_digest, result_digest));
        }

        let cascade_map: HashMap<&str, HashSet<&str>> = HashMap::from([
            (
                "declaration",
                HashSet::from([
                    "provider",
                    "package_selection",
                    "target_graph",
                    "final_resolution",
                ]),
            ),
            (
                "provider",
                HashSet::from(["package_selection", "target_graph", "final_resolution"]),
            ),
            (
                "package_selection",
                HashSet::from(["target_graph", "final_resolution"]),
            ),
            ("target_graph", HashSet::from(["final_resolution"])),
            ("final_resolution", HashSet::new()),
        ]);

        let mut recompute = HashSet::new();
        let mut queue: Vec<String> = stale_sections.iter().cloned().collect();
        while let Some(section) = queue.pop() {
            if !recompute.insert(section.clone()) {
                continue;
            }
            if let Some(downstream) = cascade_map.get(section.as_str()) {
                for downstream_section in downstream {
                    if !recompute.contains(*downstream_section) {
                        queue.push((*downstream_section).to_string());
                    }
                }
            }
        }

        let final_action_hint = if recompute.is_empty() { "reuse" } else { "update" };
        let final_input = FinalResolutionPreimage {
            dependency_name: norm.clone(),
            declaration_result_digest: section_results
                .get("declaration")
                .map(|(_, result)| result.clone())
                .unwrap_or_default(),
            package_selection_result_digest: section_results
                .get("package_selection")
                .map(|(_, result)| result.clone())
                .unwrap_or_default(),
            provider_result_digest: section_results
                .get("provider")
                .map(|(_, result)| result.clone())
                .unwrap_or_default(),
            target_graph_result_digest: section_results
                .get("target_graph")
                .map(|(_, result)| result.clone())
                .unwrap_or_default(),
        };
        let final_result = StoredFinalResolution {
            action_hint: final_action_hint,
            source_kind: resolution.source_kind.clone(),
        };
        let final_digest_in = digest_of(&final_input)?;
        let final_digest_out = digest_of(&final_result)?;

        let prior_final = prior_sections.and_then(|sections| sections.get("final_resolution"));
        if prior_final.is_none()
            || prior_final.unwrap().input_digest != final_digest_in
            || prior_final.unwrap().result_digest != final_digest_out
        {
            stale_sections.insert("final_resolution".to_string());
            recompute.insert("final_resolution".to_string());
        }

        if cfg.lock_mode == "error" && !stale_sections.is_empty() {
            state.rejections.push(RejectionRow {
                configure_request_id: cfg.configure_request_id.clone(),
                find_request_id_or_null: Some(request.find_request_id.clone()),
                reason_token: "stale_lock_section".to_string(),
                message: format!("stale_lock_section for {norm}"),
            });
            state.rejected = true;
            for section_name in SECTION_NAMES {
                let (input_digest, result_digest) = section_digests(
                    section_name,
                    decl_digest_in.as_deref(),
                    decl_digest_out.as_deref(),
                    &prov_digest_in,
                    &prov_digest_out,
                    &pkg_digest_in,
                    &pkg_digest_out,
                    &tg_digest_in,
                    &tg_digest_out,
                    &final_digest_in,
                    &final_digest_out,
                    owner.is_some(),
                );
                state.lock_section_rows.push(LockSectionRow {
                    configure_request_id: cfg.configure_request_id.clone(),
                    dependency_name: norm.clone(),
                    section: (*section_name).to_string(),
                    input_digest,
                    result_digest,
                    disposition: "rejected_stale".to_string(),
                });
            }
            continue;
        }

        for section_name in SECTION_NAMES {
            if *section_name == "declaration" && owner.is_none() {
                continue;
            }
            let (input_digest, result_digest) = section_digests(
                section_name,
                decl_digest_in.as_deref(),
                decl_digest_out.as_deref(),
                &prov_digest_in,
                &prov_digest_out,
                &pkg_digest_in,
                &pkg_digest_out,
                &tg_digest_in,
                &tg_digest_out,
                &final_digest_in,
                &final_digest_out,
                owner.is_some(),
            );
            let prior = prior_sections.and_then(|sections| sections.get(*section_name));
            let reusable = prior.is_some()
                && prior.unwrap().input_digest == input_digest
                && prior.unwrap().result_digest == result_digest
                && !recompute.contains(*section_name);
            let disposition = if reusable {
                state.reused_section_count += 1;
                "reused"
            } else {
                state.updated_section_count += 1;
                "updated"
            };
            state.lock_section_rows.push(LockSectionRow {
                configure_request_id: cfg.configure_request_id.clone(),
                dependency_name: norm.clone(),
                section: (*section_name).to_string(),
                input_digest,
                result_digest,
                disposition: disposition.to_string(),
            });
        }
    }

    if has_cycle(&all_closure_nodes, &indexes.edges) {
        return Err(FatalError::new(
            TARGET_DEPENDENCY_CYCLE,
            "cycle detected".to_string(),
        ));
    }

    state.action = if state.rejected {
        "reject_configuration".to_string()
    } else if state.updated_section_count > 0 {
        "update_resolution".to_string()
    } else {
        "reuse_resolution".to_string()
    };

    Ok(state)
}

fn section_digests(
    section_name: &str,
    decl_digest_in: Option<&str>,
    decl_digest_out: Option<&str>,
    prov_digest_in: &str,
    prov_digest_out: &str,
    pkg_digest_in: &str,
    pkg_digest_out: &str,
    tg_digest_in: &str,
    tg_digest_out: &str,
    final_digest_in: &str,
    final_digest_out: &str,
    has_owner: bool,
) -> (String, String) {
    match section_name {
        "declaration" if has_owner => (
            decl_digest_in.unwrap_or("").to_string(),
            decl_digest_out.unwrap_or("").to_string(),
        ),
        "provider" => (prov_digest_in.to_string(), prov_digest_out.to_string()),
        "package_selection" => (pkg_digest_in.to_string(), pkg_digest_out.to_string()),
        "target_graph" => (tg_digest_in.to_string(), tg_digest_out.to_string()),
        "final_resolution" => (final_digest_in.to_string(), final_digest_out.to_string()),
        _ => (String::new(), String::new()),
    }
}

fn build_declaration_rows(
    indexes: &Indexes,
    project_ids: &HashSet<String>,
) -> Vec<DeclarationRow> {
    let mut rows = Vec::new();
    for decl in &indexes.declarations {
        if !project_ids.contains(&decl.project_id) {
            continue;
        }
        let ownership = if indexes.shadowed_ids.contains(&decl.declaration_id) {
            "shadowed"
        } else {
            "owner"
        };
        rows.push(DeclarationRow {
            declaration_id: decl.declaration_id.clone(),
            project_id: decl.project_id.clone(),
            dependency_name: normalize_name(&decl.dependency_name),
            declaration_index: decl.declaration_index,
            ownership: ownership.to_string(),
            override_find_package: decl.override_find_package,
            find_package_args_enabled: decl.find_package_args.enabled,
        });
    }
    rows.sort_by(|left, right| {
        (
            left.project_id.as_str(),
            left.declaration_index,
            left.declaration_id.as_str(),
        )
            .cmp(&(
                right.project_id.as_str(),
                right.declaration_index,
                right.declaration_id.as_str(),
            ))
    });
    rows
}
