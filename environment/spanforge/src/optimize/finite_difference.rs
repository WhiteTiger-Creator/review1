//! Finite-difference gradients (starter incomplete).

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::model_schema::BridgeModel;
use crate::input::plan_schema::CalibrationPlan;
use crate::input::survey_schema::ModalSurvey;
use crate::linalg::cholesky;
use crate::objective::evaluate::ObjectiveValue;

pub fn step_size(theta_g: f64, fd: f64) -> f64 {
    fd * theta_g.abs().max(1.0)
}

pub fn objective_gradient(
    _model: &BridgeModel,
    _survey: &ModalSurvey,
    _plan: &CalibrationPlan,
    _theta: &[f64],
    _m_chol: &cholesky::Cholesky,
) -> AppResult<(Vec<f64>, ObjectiveValue)> {
    fail(
        FailureCode::EOptimization,
        "finite-difference gradient unavailable",
    )
}
