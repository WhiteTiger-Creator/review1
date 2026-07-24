//! Sensitivity Jacobian (starter incomplete).

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::model_schema::BridgeModel;
use crate::input::plan_schema::CalibrationPlan;
use crate::input::survey_schema::ModalSurvey;
use crate::linalg::cholesky;
use crate::modal::pairing::Assignment;

pub fn sensitivity_matrix(
    _model: &BridgeModel,
    _survey: &ModalSurvey,
    _plan: &CalibrationPlan,
    _theta: &[f64],
    _assignment: &Assignment,
    _m_chol: &cholesky::Cholesky,
) -> AppResult<Vec<Vec<f64>>> {
    fail(
        FailureCode::ESensitivity,
        "held-pairing sensitivity unavailable",
    )
}
