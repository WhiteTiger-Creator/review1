use std::collections::HashSet;

use crate::model::{step_kind_to_mode, ReleaseProfile, Step};

struct SimBatch {
    mode: String,
    step_count: usize,
    produced: HashSet<String>,
}

pub struct CapabilityFailure {
    pub reason: &'static str,
    pub rb_id: String,
    pub step_id: String,
    pub related_ids: Vec<String>,
}

/// Scan the complete deterministic step stream and collect failures.
/// Prefer `missing_database_capability` (rank 17) over
/// `capability_producer_order_invalid` (rank 18).
pub fn simulate_capability_batches(
    ordered_steps: &[(String, Step)],
    profile: &ReleaseProfile,
    initial_caps: &HashSet<String>,
    api_required_caps: impl Fn(&Step) -> Vec<String>,
) -> Option<CapabilityFailure> {
    let mut first_missing: Option<CapabilityFailure> = None;
    let mut first_order: Option<CapabilityFailure> = None;
    let mut sim_available = initial_caps.clone();
    let mut current: Option<SimBatch> = None;

    for (rb_id, step) in ordered_steps {
        let mode = step_kind_to_mode(&step.step_kind).unwrap().to_string();
        let needs_new = match &current {
            None => true,
            Some(batch) => {
                if batch.mode != mode {
                    true
                } else if batch.step_count >= profile.maximum_steps_per_batch as usize {
                    true
                } else if mode == "api_request" {
                    true
                } else if step.retry_mode == "idempotency_key_required" {
                    true
                } else {
                    step.required_capabilities
                        .iter()
                        .any(|cap| batch.produced.contains(cap))
                }
            }
        };
        if needs_new {
            if let Some(batch) = current.take() {
                for cap in batch.produced {
                    sim_available.insert(cap);
                }
            }
            current = Some(SimBatch {
                mode,
                step_count: 0,
                produced: HashSet::new(),
            });
        }
        let batch = current.as_mut().unwrap();
        batch.step_count += 1;
        let mut required_caps = step.required_capabilities.clone();
        required_caps.extend(api_required_caps(step));
        let mut step_failed = false;
        for cap in required_caps {
            if !sim_available.contains(&cap) {
                step_failed = true;
                if batch.produced.contains(&cap) {
                    if first_order.is_none() {
                        first_order = Some(CapabilityFailure {
                            reason: "capability_producer_order_invalid",
                            rb_id: rb_id.clone(),
                            step_id: step.step_id.clone(),
                            related_ids: vec![cap],
                        });
                    }
                } else if first_missing.is_none() {
                    first_missing = Some(CapabilityFailure {
                        reason: "missing_database_capability",
                        rb_id: rb_id.clone(),
                        step_id: step.step_id.clone(),
                        related_ids: vec![cap],
                    });
                }
                break;
            }
        }
        if !step_failed {
            batch
                .produced
                .extend(step.provided_capabilities.iter().cloned());
        }
    }
    if let Some(batch) = current.take() {
        for cap in batch.produced {
            sim_available.insert(cap);
        }
    }
    first_missing.or(first_order)
}
