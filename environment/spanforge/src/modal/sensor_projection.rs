//! Sensor projection and observed-channel intersection (starter incomplete).

use crate::input::survey_schema::MeasuredMode;
use std::collections::HashMap;

pub fn common_observed_channels(_modes: &[&MeasuredMode]) -> Option<Vec<usize>> {
    // Starter does not compute the intersection of finite channels.
    None
}

pub fn extract_measured_columns(modes: &[&MeasuredMode], channels: &[usize]) -> Vec<Vec<f64>> {
    modes
        .iter()
        .map(|m| channels.iter().map(|&i| m.shape[i].unwrap_or(0.0)).collect())
        .collect()
}

pub fn project_predicted(
    mode: &[f64],
    dof_index: &HashMap<String, usize>,
    sensors: &[String],
    channels: &[usize],
) -> Vec<f64> {
    channels
        .iter()
        .map(|&ci| {
            let sensor = &sensors[ci];
            let di = *dof_index.get(sensor).unwrap_or(&0);
            mode.get(di).copied().unwrap_or(0.0)
        })
        .collect()
}
