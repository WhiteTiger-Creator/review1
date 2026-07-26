//! Sensitivity rank (starter incomplete).

use crate::modal::pairing::Assignment;

pub fn sensitivity_scores(s: &[Vec<f64>], _assignment: &Assignment) -> Vec<f64> {
    if s.is_empty() {
        Vec::new()
    } else {
        vec![0.0; s[0].len()]
    }
}

pub fn sensitivity_ranks(scores: &[f64], _group_ids: &[String]) -> Vec<usize> {
    (0..scores.len()).map(|i| i + 1).collect()
}

pub fn numerical_rank(_s: &[Vec<f64>], _assignment: &Assignment, _rank_tol: f64) -> usize {
    0
}
