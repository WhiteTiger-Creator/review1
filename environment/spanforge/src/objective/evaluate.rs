//! Objective evaluation (starter incomplete).

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::model_schema::BridgeModel;
use crate::input::plan_schema::CalibrationPlan;
use crate::input::survey_schema::ModalSurvey;
use crate::linalg::cholesky;
use crate::modal::pairing::Assignment;

#[derive(Clone, Debug)]
pub struct ObjectiveValue {
    pub total: f64,
    pub modal: f64,
    pub regularization: f64,
    pub assignment: Assignment,
    pub predicted_clusters_len: usize,
    pub eigenvalues: Vec<f64>,
    pub frequencies: Vec<f64>,
    pub modes: Vec<Vec<f64>>,
}

pub fn evaluate(
    _model: &BridgeModel,
    _survey: &ModalSurvey,
    _plan: &CalibrationPlan,
    _theta: &[f64],
    _m_chol: &cholesky::Cholesky,
) -> AppResult<ObjectiveValue> {
    fail(
        FailureCode::EOptimization,
        "modal objective evaluation unavailable",
    )
}
