//! Calibration record assembly (starter incomplete).

use crate::input::model_schema::BridgeModel;
use crate::input::plan_schema::CalibrationPlan;
use crate::input::survey_schema::ModalSurvey;
use crate::modal::pairing::Assignment;
use crate::optimize::bounds::BoundState;
use crate::optimize::termination::TerminationState;
use crate::sensitivity::confidence::OverallConfidence;

pub struct GroupRow {
    pub group_id: String,
    pub theta: f64,
    pub lower: f64,
    pub upper: f64,
    pub reference: f64,
    pub bound_state: BoundState,
    pub group_confidence: String,
    pub sensitivity_score: f64,
    pub sensitivity_rank: usize,
}

pub struct CalibrationRecord {
    pub model_sha256: String,
    pub survey_sha256: String,
    pub plan_sha256: String,
    pub total: f64,
    pub modal: f64,
    pub regularization: f64,
    pub iterations: usize,
    pub projected_gradient_inf: f64,
    pub final_step_inf: f64,
    pub numerical_rank: usize,
    pub group_count: usize,
    pub confidence: OverallConfidence,
    pub groups: Vec<GroupRow>,
    pub assignment: Assignment,
}

pub fn build_record(
    model: &BridgeModel,
    survey: &ModalSurvey,
    plan: &CalibrationPlan,
    _theta: &[f64],
    assignment: &Assignment,
    modal: f64,
    regularization: f64,
    termination: &TerminationState,
    _sensitivity: &[Vec<f64>],
) -> CalibrationRecord {
    CalibrationRecord {
        model_sha256: model.model_sha256.clone(),
        survey_sha256: survey.survey_sha256.clone(),
        plan_sha256: plan.plan_sha256.clone(),
        total: modal + regularization,
        modal,
        regularization,
        iterations: termination.iterations,
        projected_gradient_inf: termination.projected_gradient_inf,
        final_step_inf: termination.final_step_inf,
        numerical_rank: 0,
        group_count: model.groups.len(),
        confidence: OverallConfidence::Weak,
        groups: Vec::new(),
        assignment: assignment.clone(),
    }
}
