use std::collections::HashSet;

use crate::batching::{sort_caps, BatchAccumulator};
use crate::capabilities::simulate_capability_batches;
use crate::checksum::{normalize_content_type, normalize_method, rejection_details_value, sort_utf8};
use crate::compatibility::{
    applied_status, has_checksum_drift, initial_capabilities, project_required_capabilities,
    validate_missing_idempotency_key, validate_retry_policy_only,
};
use crate::graph::{
    find_runbook_cycle, find_step_cycle, topo_runbooks, topo_steps, transitive_closure,
};
use crate::model::{
    stage_for_reason, step_kind_to_mode, BatchRow, DependencyEdgeRow, PlanRequestResult,
    PlannerInputs, Rejection, RejectionDetails, RejectionRow, ReleaseRequest, Report, RequestRow,
    SelectedRunbookRow, Step, StepRow, Summary,
};
use crate::replacement::{detect_conflicts, resolve_replacements, selection_reason};

fn make_rejection(
    request_id: &str,
    reason: &'static str,
    runbook_id_or_null: Option<String>,
    step_id_or_null: Option<String>,
    cycle_members: Option<Vec<String>>,
    related_ids: Option<Vec<String>>,
    expected_or_null: Option<String>,
    actual_or_null: Option<String>,
) -> Rejection {
    Rejection {
        request_id: request_id.to_string(),
        stage: stage_for_reason(reason).to_string(),
        reason: reason.to_string(),
        runbook_id_or_null,
        step_id_or_null,
        details: RejectionDetails {
            cycle_members: cycle_members.unwrap_or_default(),
            related_ids: related_ids.unwrap_or_default(),
            expected_or_null,
            actual_or_null,
        },
    }
}

pub fn plan_request(
    req: &ReleaseRequest,
    inputs: &PlannerInputs,
) -> (Option<PlanRequestResult>, Option<Rejection>) {
    let runbooks = &inputs.runbooks;
    let profile = &inputs.profile;
    let ops = &inputs.operations;

    let dep = match inputs.deployments.get(&req.deployment_id) {
        Some(d) => d,
        None => {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "unknown_deployment",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    };

    let direct_targets: HashSet<String> = req.target_runbook_ids.iter().cloned().collect();
    // Membership set is retained for replacement exclusion; existence checks use
    // a separate UTF-8-sorted vector so HashSet iteration cannot choose identity.
    let mut direct_target_order: Vec<String> = req.target_runbook_ids.iter().cloned().collect();
    direct_target_order.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    direct_target_order.dedup();
    for tid in &direct_target_order {
        if !runbooks.contains_key(tid) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "unknown_target_runbook",
                    Some(tid.clone()),
                    None,
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    let (selected, err, rel) = transitive_closure(&direct_targets, runbooks);
    if let Some(err) = err {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                err,
                rel.first().cloned(),
                None,
                None,
                None,
                None,
                None,
            )),
        );
    }

    if let Some(cycle) = find_runbook_cycle(&selected, runbooks) {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                "dependency_cycle",
                None,
                None,
                Some(cycle),
                None,
                None,
                None,
            )),
        );
    }

    let mut selected_sorted: Vec<String> = selected.iter().cloned().collect();
    selected_sorted.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    for rid in &selected_sorted {
        if has_checksum_drift(dep, &runbooks[rid]) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "applied_checksum_drift",
                    Some(rid.clone()),
                    None,
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    let (effective, repl_map, err, rel) = resolve_replacements(
        &selected,
        &direct_targets,
        dep,
        runbooks,
        profile,
        &req.target_api_revision,
        &req.target_database_revision,
    );
    if let Some(err) = err {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                err,
                rel.first().cloned(),
                None,
                None,
                Some(rel),
                None,
                None,
            )),
        );
    }

    if detect_conflicts(&effective, runbooks).is_some() {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                "selected_runbook_conflict",
                None,
                None,
                None,
                None,
                None,
                None,
            )),
        );
    }

    if !profile
        .supported_api_revisions
        .contains(&req.target_api_revision)
    {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                "unknown_api_revision",
                None,
                None,
                None,
                None,
                None,
                None,
            )),
        );
    }

    let mut effective_sorted: Vec<String> = effective.iter().cloned().collect();
    effective_sorted.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    for rid in &effective_sorted {
        let rb = &runbooks[rid];
        if !rb.allowed_api_revisions.contains(&req.target_api_revision) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "runbook_api_revision_forbidden",
                    Some(rid.clone()),
                    None,
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    let rb_order = topo_runbooks(&effective, runbooks, &repl_map);
    let mut executable_rbs: Vec<String> = Vec::new();
    let mut api_steps: Vec<(String, Step)> = Vec::new();
    for rid in &rb_order {
        let rb = &runbooks[rid];
        let (_, _, executable) = applied_status(dep, rb);
        if !executable {
            continue;
        }
        executable_rbs.push(rid.clone());
        let mut steps = rb.steps.clone();
        steps.sort_by(|a, b| {
            (a.step_rank, a.step_id.as_bytes()).cmp(&(b.step_rank, b.step_id.as_bytes()))
        });
        for step in steps {
            if step.step_kind == "api_request" {
                api_steps.push((rid.clone(), step));
            }
        }
    }

    for (rid, step) in &api_steps {
        let op_key = (
            req.target_api_revision.clone(),
            step.api_operation_id_or_null.clone().unwrap(),
        );
        if !ops.contains_key(&op_key) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "unknown_api_operation",
                    Some(rid.clone()),
                    Some(step.step_id.clone()),
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    for (rid, step) in &api_steps {
        let op_key = (
            req.target_api_revision.clone(),
            step.api_operation_id_or_null.clone().unwrap(),
        );
        let op = &ops[&op_key];
        let norm_method =
            normalize_method(step.http_method_or_null.as_deref().unwrap_or(""));
        if norm_method.as_deref() != Some(op.method.as_str()) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "api_method_mismatch",
                    Some(rid.clone()),
                    Some(step.step_id.clone()),
                    None,
                    None,
                    Some(op.method.clone()),
                    norm_method,
                )),
            );
        }
    }

    for (rid, step) in &api_steps {
        let op_key = (
            req.target_api_revision.clone(),
            step.api_operation_id_or_null.clone().unwrap(),
        );
        let op = &ops[&op_key];
        let norm_ct =
            normalize_content_type(step.request_content_type_or_null.as_deref().unwrap_or(""));
        let ct_ok = match &norm_ct {
            Some(ct) => op.accepted_request_content_types.contains(ct),
            None => false,
        };
        if !ct_ok {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "api_content_type_mismatch",
                    Some(rid.clone()),
                    Some(step.step_id.clone()),
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    for (rid, step) in &api_steps {
        let op_key = (
            req.target_api_revision.clone(),
            step.api_operation_id_or_null.clone().unwrap(),
        );
        let op = &ops[&op_key];
        let accepted: HashSet<i64> = step.accepted_statuses.iter().copied().collect();
        let success: HashSet<i64> = op.success_statuses.iter().copied().collect();
        if !accepted.is_subset(&success) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "api_success_status_mismatch",
                    Some(rid.clone()),
                    Some(step.step_id.clone()),
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    if !profile
        .supported_database_revisions
        .contains(&req.target_database_revision)
    {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                "database_revision_mismatch",
                None,
                None,
                None,
                None,
                None,
                None,
            )),
        );
    }
    if dep.database_revision != req.target_database_revision {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                "database_revision_mismatch",
                None,
                None,
                None,
                None,
                None,
                None,
            )),
        );
    }

    for rid in &effective_sorted {
        let rb = &runbooks[rid];
        if !rb
            .allowed_database_revisions
            .contains(&req.target_database_revision)
        {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "runbook_database_revision_forbidden",
                    Some(rid.clone()),
                    None,
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    for rid in &executable_rbs {
        let rb = &runbooks[rid];
        let step_ids: HashSet<String> = rb.steps.iter().map(|s| s.step_id.clone()).collect();
        let mut steps = rb.steps.clone();
        steps.sort_by(|a, b| {
            (a.step_rank, a.step_id.as_bytes()).cmp(&(b.step_rank, b.step_id.as_bytes()))
        });
        for s in &steps {
            if s.requires_step_ids.contains(&s.step_id) {
                return (
                    None,
                    Some(make_rejection(
                        &req.request_id,
                        "invalid_step_dependency",
                        Some(rid.clone()),
                        Some(s.step_id.clone()),
                        None,
                        None,
                        None,
                        None,
                    )),
                );
            }
            for dep_sid in &s.requires_step_ids {
                if !step_ids.contains(dep_sid) {
                    return (
                        None,
                        Some(make_rejection(
                            &req.request_id,
                            "invalid_step_dependency",
                            Some(rid.clone()),
                            Some(s.step_id.clone()),
                            None,
                            Some(vec![dep_sid.clone()]),
                            None,
                            None,
                        )),
                    );
                }
            }
        }
        if let Some(cycle_steps) = find_step_cycle(&rb.steps) {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "invalid_step_dependency",
                    Some(rid.clone()),
                    None,
                    Some(cycle_steps),
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    let mut ordered_steps: Vec<(String, Step)> = Vec::new();
    for rid in &executable_rbs {
        for step in topo_steps(&runbooks[rid].steps) {
            ordered_steps.push((rid.clone(), step));
        }
    }

    let caps = initial_capabilities(dep, runbooks);

    let api_caps = |step: &Step| -> Vec<String> {
        if step.step_kind == "api_request" {
            let op_key = (
                req.target_api_revision.clone(),
                step.api_operation_id_or_null.clone().unwrap(),
            );
            ops.get(&op_key)
                .map(|op| op.required_capabilities.clone())
                .unwrap_or_default()
        } else {
            Vec::new()
        }
    };

    if let Some(failure) = simulate_capability_batches(&ordered_steps, profile, &caps, api_caps) {
        return (
            None,
            Some(make_rejection(
                &req.request_id,
                failure.reason,
                Some(failure.rb_id),
                Some(failure.step_id),
                None,
                Some(failure.related_ids),
                None,
                None,
            )),
        );
    }

    for (rid, step) in &ordered_steps {
        let op = if step.step_kind == "api_request" {
            let op_key = (
                req.target_api_revision.clone(),
                step.api_operation_id_or_null.clone().unwrap(),
            );
            ops.get(&op_key)
        } else {
            None
        };
        if validate_retry_policy_only(step, op).is_some() {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "invalid_retry_policy",
                    Some(rid.clone()),
                    Some(step.step_id.clone()),
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    for (rid, step) in &ordered_steps {
        if validate_missing_idempotency_key(step).is_some() {
            return (
                None,
                Some(make_rejection(
                    &req.request_id,
                    "missing_idempotency_key_source",
                    Some(rid.clone()),
                    Some(step.step_id.clone()),
                    None,
                    None,
                    None,
                    None,
                )),
            );
        }
    }

    let mut selected_rows = Vec::new();

    let mut topo_pos = 1usize;
    let mut effective_list: Vec<String> = effective.iter().cloned().collect();
    effective_list.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    for rid in effective_list {
        let rb = &runbooks[&rid];
        let (mut status, already, executable) = applied_status(dep, rb);
        if status == "drift" {
            status = "not_applied".to_string();
        }
        let topo = if executable {
            let pos = topo_pos;
            topo_pos += 1;
            Some(pos)
        } else {
            None
        };
        let replaces: Vec<String> = repl_map
            .iter()
            .filter(|(_, v)| *v == &rid)
            .map(|(k, _)| k.clone())
            .collect();
        selected_rows.push(SelectedRunbookRow {
            request_id: req.request_id.clone(),
            runbook_id: rid.clone(),
            selection_reason: selection_reason(&rid, &direct_targets, &repl_map),
            checksum_status: status,
            already_applied: already,
            executable,
            topological_position_or_null: topo,
            replaces_runbook_ids: sort_utf8(&replaces),
        });
    }
    selected_rows.sort_by(|a, b| {
        (
            a.request_id.as_str(),
            a.already_applied,
            a.topological_position_or_null.unwrap_or(10usize.pow(9)),
            a.runbook_id.as_bytes(),
        )
            .cmp(&(
                b.request_id.as_str(),
                b.already_applied,
                b.topological_position_or_null.unwrap_or(10usize.pow(9)),
                b.runbook_id.as_bytes(),
            ))
    });

    let mut edge_rows = Vec::new();
    let mut effective_list2: Vec<String> = effective.iter().cloned().collect();
    effective_list2.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    for rid in effective_list2 {
        let rb = &runbooks[&rid];
        for raw_dep in &rb.requires {
            if let Some(new_id) = repl_map.get(raw_dep) {
                if effective.contains(new_id) {
                    edge_rows.push(DependencyEdgeRow {
                        request_id: req.request_id.clone(),
                        from_runbook_id: rid.clone(),
                        to_runbook_id: raw_dep.clone(),
                        edge_type: "replacement_provides".to_string(),
                        satisfied_by_runbook_id: new_id.clone(),
                    });
                }
            } else if effective.contains(raw_dep) {
                edge_rows.push(DependencyEdgeRow {
                    request_id: req.request_id.clone(),
                    from_runbook_id: rid.clone(),
                    to_runbook_id: raw_dep.clone(),
                    edge_type: "requires".to_string(),
                    satisfied_by_runbook_id: raw_dep.clone(),
                });
            }
        }
    }
    edge_rows.sort_by(|a, b| {
        (
            a.request_id.as_str(),
            a.from_runbook_id.as_bytes(),
            a.to_runbook_id.as_bytes(),
            a.edge_type.as_bytes(),
            a.satisfied_by_runbook_id.as_bytes(),
        )
            .cmp(&(
                b.request_id.as_str(),
                b.from_runbook_id.as_bytes(),
                b.to_runbook_id.as_bytes(),
                b.edge_type.as_bytes(),
                b.satisfied_by_runbook_id.as_bytes(),
            ))
    });

    let mut step_rows = Vec::new();
    let mut batch_rows = Vec::new();
    let mut global_pos = 1usize;
    let mut builder = BatchAccumulator::new();

    for (rb_id, step) in &ordered_steps {
        builder.add_step(rb_id, step, profile, &ordered_steps);
        let batch_index = builder.current_batch_index();
        let mode = step_kind_to_mode(&step.step_kind).unwrap().to_string();
        step_rows.push(StepRow {
            request_id: req.request_id.clone(),
            runbook_id: rb_id.clone(),
            step_id: step.step_id.clone(),
            global_step_position: global_pos,
            step_kind: step.step_kind.clone(),
            execution_mode: mode,
            retry_mode: step.retry_mode.clone(),
            api_operation_id_or_null: step.api_operation_id_or_null.clone(),
            required_capabilities: project_required_capabilities(
                &step.required_capabilities,
                &caps,
            ),
            provided_capabilities: sort_utf8(&step.provided_capabilities),
            batch_index,
        });
        global_pos += 1;
    }

    for (idx, batch) in builder.finish(&ordered_steps).into_iter().enumerate() {
        let declared: Vec<String> = batch.required_capabilities.into_iter().collect();
        batch_rows.push(BatchRow {
            request_id: req.request_id.clone(),
            batch_index: idx,
            execution_mode: batch.execution_mode,
            runbook_ids: batch.runbook_ids,
            step_ids: batch.step_ids,
            retry_mode: batch.retry_mode,
            required_capabilities: project_required_capabilities(&declared, &caps),
            produced_capabilities: sort_caps(&batch.produced_capabilities),
        });
    }

    let request_row = RequestRow {
        request_id: req.request_id.clone(),
        deployment_id: req.deployment_id.clone(),
        target_api_revision: req.target_api_revision.clone(),
        target_database_revision: req.target_database_revision.clone(),
        status: "accepted".to_string(),
        reason_or_null: None,
        selected_runbook_count: effective.len(),
        executable_runbook_count: executable_rbs.len(),
        executable_step_count: step_rows.len(),
        batch_count: batch_rows.len(),
    };

    (
        Some(PlanRequestResult {
            request_row,
            selected_runbook_rows: selected_rows,
            dependency_edge_rows: edge_rows,
            step_rows,
            batch_rows,
        }),
        None,
    )
}

pub fn compute_summary(report: &Report) -> Summary {
    Summary {
        request_count: report.request_rows.len(),
        accepted_request_count: report
            .request_rows
            .iter()
            .filter(|r| r.status == "accepted")
            .count(),
        rejected_request_count: report
            .request_rows
            .iter()
            .filter(|r| r.status == "rejected")
            .count(),
        selected_runbook_count: report.selected_runbook_rows.len(),
        executable_runbook_count: report
            .selected_runbook_rows
            .iter()
            .filter(|r| r.executable)
            .count(),
        executable_step_count: report.step_rows.len(),
        local_batch_count: report
            .batch_rows
            .iter()
            .filter(|b| b.execution_mode == "local")
            .count(),
        api_request_batch_count: report
            .batch_rows
            .iter()
            .filter(|b| b.execution_mode == "api_request")
            .count(),
        database_transaction_batch_count: report
            .batch_rows
            .iter()
            .filter(|b| b.execution_mode == "database_transaction")
            .count(),
        checksum_drift_count: report
            .rejection_rows
            .iter()
            .filter(|r| r.reason == "applied_checksum_drift")
            .count(),
    }
}

pub fn plan_all(inputs: &PlannerInputs) -> Report {
    let mut report = Report {
        request_rows: Vec::new(),
        selected_runbook_rows: Vec::new(),
        dependency_edge_rows: Vec::new(),
        step_rows: Vec::new(),
        batch_rows: Vec::new(),
        rejection_rows: Vec::new(),
        summary: Summary {
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
        },
    };

    let mut requests = inputs.requests.clone();
    requests.sort_by(|a, b| a.request_id.as_bytes().cmp(b.request_id.as_bytes()));

    for req in requests {
        let (result, rejection) = plan_request(&req, inputs);
        if let Some(rej) = rejection {
            report.request_rows.push(RequestRow {
                request_id: req.request_id.clone(),
                deployment_id: req.deployment_id.clone(),
                target_api_revision: req.target_api_revision.clone(),
                target_database_revision: req.target_database_revision.clone(),
                status: "rejected".to_string(),
                reason_or_null: Some(rej.reason.clone()),
                selected_runbook_count: 0,
                executable_runbook_count: 0,
                executable_step_count: 0,
                batch_count: 0,
            });
            report.rejection_rows.push(RejectionRow {
                request_id: rej.request_id,
                stage: rej.stage,
                reason: rej.reason,
                runbook_id_or_null: rej.runbook_id_or_null,
                step_id_or_null: rej.step_id_or_null,
                details: rejection_details_value(&rej.details),
            });
        } else if let Some(result) = result {
            report.request_rows.push(result.request_row);
            report
                .selected_runbook_rows
                .extend(result.selected_runbook_rows);
            report
                .dependency_edge_rows
                .extend(result.dependency_edge_rows);
            report.step_rows.extend(result.step_rows);
            report.batch_rows.extend(result.batch_rows);
        }
    }

    report
        .request_rows
        .sort_by(|a, b| a.request_id.as_bytes().cmp(b.request_id.as_bytes()));
    report.rejection_rows.sort_by(|a, b| {
        (
            a.request_id.as_bytes(),
            a.stage.as_bytes(),
            a.reason.as_bytes(),
            a.runbook_id_or_null.is_some(),
            a.runbook_id_or_null.as_deref().unwrap_or(""),
            a.step_id_or_null.is_some(),
            a.step_id_or_null.as_deref().unwrap_or(""),
        )
            .cmp(&(
                b.request_id.as_bytes(),
                b.stage.as_bytes(),
                b.reason.as_bytes(),
                b.runbook_id_or_null.is_some(),
                b.runbook_id_or_null.as_deref().unwrap_or(""),
                b.step_id_or_null.is_some(),
                b.step_id_or_null.as_deref().unwrap_or(""),
            ))
    });
    report.summary = compute_summary(&report);
    report
}
