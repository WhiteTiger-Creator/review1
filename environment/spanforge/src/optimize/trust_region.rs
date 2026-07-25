//! Bounded trust-region search (starter incomplete).

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::model_schema::BridgeModel;
use crate::input::plan_schema::CalibrationPlan;
use crate::input::survey_schema::ModalSurvey;
use crate::linalg::cholesky;
use crate::objective::evaluate::ObjectiveValue;
use crate::optimize::termination::TerminationState;

pub struct OptimizeResult {
    pub theta: Vec<f64>,
    pub objective: ObjectiveValue,
    pub termination: TerminationState,
}

pub fn calibrate_parameters(
    _model: &BridgeModel,
    _survey: &ModalSurvey,
    _plan: &CalibrationPlan,
    _m_chol: &cholesky::Cholesky,
) -> AppResult<OptimizeResult> {
    fail(
        FailureCode::EOptimization,
        "projected bounded optimization unavailable",
    )
}
