//! Global cluster assignment (starter incomplete).

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::plan_schema::CalibrationPlan;
use crate::input::survey_schema::ModalSurvey;
use crate::modal::cluster::Cluster;
use std::collections::HashMap;

#[derive(Clone, Debug)]
pub struct Pairing {
    pub measured_cluster_index: usize,
    pub predicted_cluster_index: usize,
    pub measured_ids_csv: String,
    pub predicted_ordinals_csv: String,
    pub measured_centroid_hz: f64,
    pub predicted_centroid_hz: f64,
    pub frequency_residual: f64,
    pub subspace_mac: f64,
    pub pair_cost: f64,
    pub measured_weight: f64,
}

#[derive(Clone, Debug)]
pub struct Assignment {
    pub pairs: Vec<Pairing>,
    pub modal_cost: f64,
}

pub fn global_assign(
    _survey: &ModalSurvey,
    _measured_clusters: &[Cluster],
    _predicted_clusters: &[Cluster],
    _predicted_modes: &[Vec<f64>],
    _predicted_freqs: &[f64],
    _dof_index: &HashMap<String, usize>,
    _plan: &CalibrationPlan,
) -> AppResult<Assignment> {
    fail(
        FailureCode::EModalPairing,
        "global cluster assignment unavailable",
    )
}
