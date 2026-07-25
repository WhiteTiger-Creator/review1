//! Typed input and report models.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

// --- Input documents ---

#[derive(Debug, Clone, Deserialize)]
pub struct DeclarationsDoc {
    pub declarations: Vec<Declaration>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Declaration {
    pub declaration_id: String,
    pub project_id: String,
    pub dependency_name: String,
    pub declaration_index: i64,
    pub source_kind: String,
    pub source_identity: String,
    pub declared_version_or_null: Option<String>,
    #[serde(default)]
    pub override_find_package: bool,
    pub find_package_args: FindPackageArgs,
    #[serde(default)]
    pub produced_targets: Vec<String>,
    pub content_digest: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FindPackageArgs {
    pub enabled: bool,
    pub try_system_first: bool,
    #[serde(default)]
    pub components: Vec<String>,
    pub version_or_null: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct FindRequest {
    pub find_request_id: String,
    pub project_id: String,
    pub dependency_name: String,
    pub request_index: i64,
    #[serde(default = "default_true")]
    pub required: bool,
    #[serde(default)]
    pub exact: bool,
    pub version_or_null: Option<String>,
    #[serde(default)]
    pub components: Vec<String>,
    #[serde(default)]
    pub bypass_provider: bool,
    pub request_kind: String,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProviderResponsesDoc {
    pub providers: Vec<ProviderConfig>,
    pub responses: Vec<ProviderResponse>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProviderConfig {
    pub provider_config_id: String,
    #[serde(default)]
    pub intercept_find_package: bool,
    #[serde(default)]
    pub intercept_fetchcontent: bool,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProviderResponse {
    pub response_id: String,
    pub provider_config_id: String,
    pub dependency_name: String,
    pub request_kind: String,
    #[serde(default)]
    pub satisfies: bool,
    pub version_or_null: Option<String>,
    #[serde(default)]
    pub provided_components: Vec<String>,
    #[serde(default)]
    pub produced_targets: Vec<String>,
    pub source_identity: String,
    pub content_digest: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PackageCandidatesDoc {
    pub candidates: Vec<PackageCandidate>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PackageCandidate {
    pub candidate_id: String,
    pub dependency_name: String,
    pub version: String,
    pub compatibility: String,
    #[serde(default)]
    pub provided_components: Vec<String>,
    #[serde(default)]
    pub produced_targets: Vec<String>,
    pub config_path: String,
    pub content_digest: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceOverridesDoc {
    pub overrides: Vec<SourceOverride>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SourceOverride {
    pub override_id: String,
    pub dependency_name: String,
    pub source_dir: String,
    pub active: bool,
    #[serde(default)]
    pub produced_targets: Vec<String>,
    #[serde(default)]
    pub provided_components: Vec<String>,
    pub version_or_null: Option<String>,
    pub content_digest: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TargetGraphDoc {
    #[serde(default)]
    pub targets: Vec<TargetNode>,
    #[serde(default)]
    pub edges: Vec<TargetEdge>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TargetNode {
    pub target_id: String,
    pub producer_dependency: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TargetEdge {
    pub from_target: String,
    pub to_target: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PreviousLocksDoc {
    pub locks: Vec<LockObject>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LockObject {
    pub lock_id: String,
    pub project_id: String,
    #[serde(default)]
    pub sections_by_dependency: BTreeMap<String, BTreeMap<String, LockSection>>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LockSection {
    pub input_digest: String,
    pub result_digest: String,
    #[serde(default)]
    pub stored_result: Value,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PolicyDoc {
    pub schema_version: i64,
    pub configure_requests: Vec<ConfigureRequest>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ConfigureRequest {
    pub configure_request_id: String,
    pub request_index: i64,
    pub project_id: String,
    pub provider_config_id: String,
    pub lock_mode: String,
    pub previous_lock_id_or_null: Option<String>,
    pub find_request_ids: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct LoadedData {
    pub declarations: Vec<Declaration>,
    pub find_requests: Vec<FindRequest>,
    pub providers: Vec<ProviderConfig>,
    pub provider_responses: Vec<ProviderResponse>,
    pub candidates: Vec<PackageCandidate>,
    pub overrides: Vec<SourceOverride>,
    pub target_graph: TargetGraphDoc,
    pub locks: Vec<LockObject>,
    pub policy: PolicyDoc,
}

// --- Report output ---

#[derive(Debug, Clone, Serialize)]
pub struct Report {
    pub schema_version: i64,
    pub request_rows: Vec<RequestRow>,
    pub declaration_rows: Vec<DeclarationRow>,
    pub provider_rows: Vec<ProviderRow>,
    pub package_selection_rows: Vec<PackageSelectionRow>,
    pub target_rows: Vec<TargetRow>,
    pub lock_section_rows: Vec<LockSectionRow>,
    pub rejection_rows: Vec<RejectionRow>,
    pub summary: Summary,
}

#[derive(Debug, Clone, Serialize)]
pub struct RequestRow {
    pub configure_request_id: String,
    pub request_index: i64,
    pub project_id: String,
    pub provider_config_id: String,
    pub lock_mode: String,
    pub action: String,
    pub resolved_dependency_count: i64,
    pub reused_section_count: i64,
    pub updated_section_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct DeclarationRow {
    pub declaration_id: String,
    pub project_id: String,
    pub dependency_name: String,
    pub declaration_index: i64,
    pub ownership: String,
    pub override_find_package: bool,
    pub find_package_args_enabled: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProviderRow {
    pub configure_request_id: String,
    pub find_request_id: String,
    pub dependency_name: String,
    pub intercepted: bool,
    pub bypass_provider: bool,
    pub response_id_or_null: Option<String>,
    pub satisfies_or_null: Option<bool>,
    pub outcome: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PackageSelectionRow {
    pub configure_request_id: String,
    pub find_request_id: String,
    pub dependency_name: String,
    pub source_kind: String,
    pub identity_or_null: Option<String>,
    pub version_or_null: Option<String>,
    pub components: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TargetRow {
    pub configure_request_id: String,
    pub dependency_name: String,
    pub target_id: String,
    pub role: String,
    pub producer_dependency: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LockSectionRow {
    pub configure_request_id: String,
    pub dependency_name: String,
    pub section: String,
    pub input_digest: String,
    pub result_digest: String,
    pub disposition: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RejectionRow {
    pub configure_request_id: String,
    pub find_request_id_or_null: Option<String>,
    pub reason_token: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Summary {
    pub configure_request_count: i64,
    pub reuse_count: i64,
    pub update_count: i64,
    pub reject_count: i64,
    pub declaration_owner_count: i64,
    pub target_row_count: i64,
}
