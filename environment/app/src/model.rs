use std::collections::{HashMap, HashSet};

use serde::Serialize;
use serde_json::Value;

pub const LOCAL_RETRY: &[&str] = &["never", "safe"];
pub const DB_READ_RETRY: &[&str] = &["never", "safe"];
pub const DB_WRITE_RETRY: &[&str] = &["never"];
pub const API_RETRY: &[&str] = &["never", "safe", "idempotency_key_required"];

pub fn step_kind_to_mode(kind: &str) -> Option<&'static str> {
    match kind {
        "local_prepare" | "local_finalize" => Some("local"),
        "api_request" => Some("api_request"),
        "database_read" | "database_write" => Some("database_transaction"),
        _ => None,
    }
}

pub fn stage_for_reason(reason: &str) -> &'static str {
    match reason {
        "unknown_deployment" => "deployment",
        "unknown_target_runbook" => "target",
        "missing_dependency" => "dependency",
        "dependency_cycle" => "graph",
        "applied_checksum_drift" => "checksum",
        "replacement_unsatisfied" => "replacement",
        "selected_runbook_conflict" => "conflict",
        "unknown_api_revision"
        | "runbook_api_revision_forbidden"
        | "unknown_api_operation"
        | "api_method_mismatch"
        | "api_content_type_mismatch"
        | "api_success_status_mismatch" => "api",
        "database_revision_mismatch" | "runbook_database_revision_forbidden" => "database",
        "invalid_step_dependency" => "step_graph",
        "missing_database_capability" | "capability_producer_order_invalid" => "capability",
        "invalid_retry_policy" | "missing_idempotency_key_source" => "retry",
        "batch_construction_failed" => "batching",
        _ => "unknown",
    }
}

#[derive(Debug, Clone)]
pub struct Step {
    pub step_id: String,
    pub step_rank: i64,
    pub step_kind: String,
    pub requires_step_ids: Vec<String>,
    pub required_capabilities: Vec<String>,
    pub provided_capabilities: Vec<String>,
    pub api_operation_id_or_null: Option<String>,
    pub http_method_or_null: Option<String>,
    pub request_content_type_or_null: Option<String>,
    pub accepted_statuses: Vec<i64>,
    pub database_action_or_null: Option<String>,
    pub retry_mode: String,
    pub idempotency_key_source_or_null: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Runbook {
    pub runbook_id: String,
    pub version: String,
    pub checksum_sha256: String,
    pub plan_rank: i64,
    pub requires: Vec<String>,
    pub conflicts: Vec<String>,
    pub replaces: Vec<String>,
    pub provides_runbook_ids: Vec<String>,
    pub allowed_api_revisions: Vec<String>,
    pub allowed_database_revisions: Vec<String>,
    pub steps: Vec<Step>,
}

#[derive(Debug, Clone)]
pub struct ReleaseProfile {
    pub release_profile_version: String,
    pub maximum_runbooks_per_request: i64,
    pub maximum_steps_per_batch: i64,
    pub supported_api_revisions: Vec<String>,
    pub supported_database_revisions: Vec<String>,
    pub allowed_retry_modes: Vec<String>,
    pub allowed_execution_modes: Vec<String>,
    pub required_checksum_algorithm: String,
    pub canonical_json_format: String,
    pub replacement_preferences: HashMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct ApiOperation {
    pub operation_id: String,
    pub api_revision: String,
    pub path: String,
    pub method: String,
    pub accepted_request_content_types: Vec<String>,
    pub success_statuses: Vec<i64>,
    pub idempotent: bool,
    pub required_capabilities: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct ReleaseRequest {
    pub request_id: String,
    pub deployment_id: String,
    pub target_runbook_ids: Vec<String>,
    pub target_api_revision: String,
    pub target_database_revision: String,
}

#[derive(Debug, Clone)]
pub struct Deployment {
    pub deployment_id: String,
    pub database_revision: String,
    pub capability_profile_version: String,
    pub capabilities: HashSet<String>,
    pub applied_runbooks: HashMap<String, String>,
}

#[derive(Debug, Clone)]
pub struct RejectionDetails {
    pub cycle_members: Vec<String>,
    pub related_ids: Vec<String>,
    pub expected_or_null: Option<String>,
    pub actual_or_null: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Rejection {
    pub request_id: String,
    pub stage: String,
    pub reason: String,
    pub runbook_id_or_null: Option<String>,
    pub step_id_or_null: Option<String>,
    pub details: RejectionDetails,
}

#[derive(Debug, Clone)]
pub struct PlannerInputs {
    pub runbooks: HashMap<String, Runbook>,
    pub profile: ReleaseProfile,
    pub operations: HashMap<(String, String), ApiOperation>,
    pub deployments: HashMap<String, Deployment>,
    pub requests: Vec<ReleaseRequest>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RequestRow {
    pub request_id: String,
    pub deployment_id: String,
    pub target_api_revision: String,
    pub target_database_revision: String,
    pub status: String,
    pub reason_or_null: Option<String>,
    pub selected_runbook_count: usize,
    pub executable_runbook_count: usize,
    pub executable_step_count: usize,
    pub batch_count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct SelectedRunbookRow {
    pub request_id: String,
    pub runbook_id: String,
    pub selection_reason: String,
    pub checksum_status: String,
    pub already_applied: bool,
    pub executable: bool,
    pub topological_position_or_null: Option<usize>,
    pub replaces_runbook_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DependencyEdgeRow {
    pub request_id: String,
    pub from_runbook_id: String,
    pub to_runbook_id: String,
    pub edge_type: String,
    pub satisfied_by_runbook_id: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StepRow {
    pub request_id: String,
    pub runbook_id: String,
    pub step_id: String,
    pub global_step_position: usize,
    pub step_kind: String,
    pub execution_mode: String,
    pub retry_mode: String,
    pub api_operation_id_or_null: Option<String>,
    pub required_capabilities: Vec<String>,
    pub provided_capabilities: Vec<String>,
    pub batch_index: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct BatchRow {
    pub request_id: String,
    pub batch_index: usize,
    pub execution_mode: String,
    pub runbook_ids: Vec<String>,
    pub step_ids: Vec<String>,
    pub retry_mode: String,
    pub required_capabilities: Vec<String>,
    pub produced_capabilities: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RejectionRow {
    pub request_id: String,
    pub stage: String,
    pub reason: String,
    pub runbook_id_or_null: Option<String>,
    pub step_id_or_null: Option<String>,
    pub details: Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct Summary {
    pub request_count: usize,
    pub accepted_request_count: usize,
    pub rejected_request_count: usize,
    pub selected_runbook_count: usize,
    pub executable_runbook_count: usize,
    pub executable_step_count: usize,
    pub local_batch_count: usize,
    pub api_request_batch_count: usize,
    pub database_transaction_batch_count: usize,
    pub checksum_drift_count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct Report {
    pub request_rows: Vec<RequestRow>,
    pub selected_runbook_rows: Vec<SelectedRunbookRow>,
    pub dependency_edge_rows: Vec<DependencyEdgeRow>,
    pub step_rows: Vec<StepRow>,
    pub batch_rows: Vec<BatchRow>,
    pub rejection_rows: Vec<RejectionRow>,
    pub summary: Summary,
}

#[derive(Debug, Clone)]
pub struct PlanRequestResult {
    pub request_row: RequestRow,
    pub selected_runbook_rows: Vec<SelectedRunbookRow>,
    pub dependency_edge_rows: Vec<DependencyEdgeRow>,
    pub step_rows: Vec<StepRow>,
    pub batch_rows: Vec<BatchRow>,
}
