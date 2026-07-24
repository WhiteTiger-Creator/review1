//! Release report assembly.
//! Full dependency closure, replacement, compatibility, capability, retry, and
//! batch planning remain incomplete in the starter.

use crate::model::{PlannerInputs, RejectionRow, Report, RequestRow, Summary};

fn empty_summary() -> Summary {
    Summary {
        request_count: 0,
        accepted_request_count: 0,
        rejected_request_count: 0,
        selected_runbook_count: 0,
        executable_runbook_count: 0,
        executable_step_count: 0,
        local_batch_count: 0,
        api_request_batch_count: 0,
        database_transaction_batch_count: 0,
        checksum_drift_count: 0,
    }
}

/// Builds a structurally valid but incomplete report.
/// Starter behavior: every request is rejected with a placeholder reason so the
/// CLI can emit a report while remaining visibly unfinished.
pub fn plan_all(inputs: &PlannerInputs) -> Report {
    let mut report = Report {
        request_rows: Vec::new(),
        selected_runbook_rows: Vec::new(),
        dependency_edge_rows: Vec::new(),
        step_rows: Vec::new(),
        batch_rows: Vec::new(),
        rejection_rows: Vec::new(),
        summary: empty_summary(),
    };

    let mut requests = inputs.requests.clone();
    requests.sort_by(|a, b| a.request_id.as_bytes().cmp(b.request_id.as_bytes()));

    for req in requests {
        report.request_rows.push(RequestRow {
            request_id: req.request_id.clone(),
            deployment_id: req.deployment_id.clone(),
            target_api_revision: req.target_api_revision.clone(),
            target_database_revision: req.target_database_revision.clone(),
            status: "rejected".to_string(),
            reason_or_null: Some("batch_construction_failed".to_string()),
            selected_runbook_count: 0,
            executable_runbook_count: 0,
            executable_step_count: 0,
            batch_count: 0,
        });
        report.rejection_rows.push(RejectionRow {
            request_id: req.request_id.clone(),
            stage: "batching".to_string(),
            reason: "batch_construction_failed".to_string(),
            runbook_id_or_null: None,
            step_id_or_null: None,
            details: serde_json::json!({
                "actual_or_null": null,
                "cycle_members": [],
                "expected_or_null": null,
                "related_ids": [],
            }),
        });
    }

    report.summary.request_count = report.request_rows.len();
    report.summary.rejected_request_count = report.request_rows.len();
    report
}
