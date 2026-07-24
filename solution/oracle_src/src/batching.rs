use std::collections::HashSet;

use crate::checksum::sort_utf8;
use crate::model::{step_kind_to_mode, ReleaseProfile, Step};

#[derive(Clone)]
pub struct BatchState {
    pub execution_mode: String,
    pub runbook_ids: Vec<String>,
    pub step_ids: Vec<String>,
    pub retry_mode: String,
    pub required_capabilities: HashSet<String>,
    pub produced_capabilities: HashSet<String>,
}

fn needs_new_batch(current: Option<&BatchState>, step: &Step, profile: &ReleaseProfile) -> bool {
    let mode = step_kind_to_mode(&step.step_kind).unwrap();
    match current {
        None => true,
        Some(batch) => {
            if batch.execution_mode != mode {
                return true;
            }
            if batch.step_ids.len() >= profile.maximum_steps_per_batch as usize {
                return true;
            }
            if mode == "api_request" {
                return true;
            }
            if step.retry_mode == "idempotency_key_required" {
                return true;
            }
            for cap in &step.required_capabilities {
                if batch.produced_capabilities.contains(cap) {
                    return true;
                }
            }
            false
        }
    }
}

fn batch_retry_mode(mode: &str, step_ids: &[String], ordered_steps: &[(String, Step)]) -> String {
    if mode == "local" || mode == "database_transaction" {
        let steps_in_batch: Vec<&Step> = ordered_steps
            .iter()
            .filter(|(_, s)| step_ids.contains(&s.step_id))
            .map(|(_, s)| s)
            .collect();
        if steps_in_batch.iter().all(|s| s.retry_mode == "safe") {
            "safe".to_string()
        } else {
            "never".to_string()
        }
    } else {
        ordered_steps
            .iter()
            .find(|(_, s)| step_ids.contains(&s.step_id))
            .map(|(_, s)| s.retry_mode.clone())
            .unwrap_or_else(|| "never".to_string())
    }
}

pub struct BatchAccumulator {
    current: Option<BatchState>,
    batch_idx: usize,
    completed: Vec<BatchState>,
}

impl BatchAccumulator {
    pub fn new() -> Self {
        Self {
            current: None,
            batch_idx: 0,
            completed: Vec::new(),
        }
    }

    pub fn current_batch_index(&self) -> usize {
        self.batch_idx
    }

    pub fn finalize_current(&mut self) {
        if let Some(mut batch) = self.current.take() {
            if batch.execution_mode == "local" || batch.execution_mode == "database_transaction" {
                batch.retry_mode = batch_retry_mode(&batch.execution_mode, &batch.step_ids, &[]);
            }
            self.completed.push(batch);
            self.batch_idx += 1;
        }
    }

    pub fn add_step(
        &mut self,
        rb_id: &str,
        step: &Step,
        profile: &ReleaseProfile,
        ordered_steps: &[(String, Step)],
    ) {
        if needs_new_batch(self.current.as_ref(), step, profile) {
            self.finalize_current_with_ordered(ordered_steps);
            let mode = step_kind_to_mode(&step.step_kind).unwrap().to_string();
            self.current = Some(BatchState {
                execution_mode: mode,
                runbook_ids: Vec::new(),
                step_ids: Vec::new(),
                retry_mode: step.retry_mode.clone(),
                required_capabilities: HashSet::new(),
                produced_capabilities: HashSet::new(),
            });
        }
        let batch = self.current.as_mut().unwrap();
        if !batch.runbook_ids.iter().any(|id| id == rb_id) {
            batch.runbook_ids.push(rb_id.to_string());
        }
        batch.step_ids.push(step.step_id.clone());
        batch
            .required_capabilities
            .extend(step.required_capabilities.iter().cloned());
        batch
            .produced_capabilities
            .extend(step.provided_capabilities.iter().cloned());
        if batch.execution_mode == "local" || batch.execution_mode == "database_transaction" {
            batch.retry_mode =
                batch_retry_mode(&batch.execution_mode, &batch.step_ids, ordered_steps);
        }
    }

    fn finalize_current_with_ordered(&mut self, ordered_steps: &[(String, Step)]) {
        if let Some(mut batch) = self.current.take() {
            if batch.execution_mode == "local" || batch.execution_mode == "database_transaction" {
                batch.retry_mode =
                    batch_retry_mode(&batch.execution_mode, &batch.step_ids, ordered_steps);
            }
            self.completed.push(batch);
            self.batch_idx += 1;
        }
    }

    pub fn finish(mut self, ordered_steps: &[(String, Step)]) -> Vec<BatchState> {
        self.finalize_current_with_ordered(ordered_steps);
        self.completed
    }
}

pub fn sort_caps(set: &HashSet<String>) -> Vec<String> {
    sort_utf8(&set.iter().cloned().collect::<Vec<_>>())
}
