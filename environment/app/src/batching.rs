//! Execution batch construction.
//! Mode isolation, size limits, and capability boundaries are intentionally incomplete.

#![allow(dead_code)]

use crate::model::Step;

/// Returns the raw step list without constructing batches.
pub fn steps_as_flat_list(steps: &[Step]) -> Vec<String> {
    steps.iter().map(|s| s.step_id.clone()).collect()
}
