//! Convergence certification (starter incomplete).

use crate::input::plan_schema::CalibrationPlan;

#[derive(Clone, Debug)]
pub struct TerminationState {
    pub iterations: usize,
    pub projected_gradient_inf: f64,
    pub final_step_inf: f64,
    pub converged: bool,
}

pub fn check(
    _plan: &CalibrationPlan,
    iterations: usize,
    _projected_grad: &[f64],
    _step: &[f64],
    _obj_decrease: f64,
) -> TerminationState {
    TerminationState {
        iterations,
        projected_gradient_inf: f64::INFINITY,
        final_step_inf: f64::INFINITY,
        converged: false,
    }
}
