//! Regularization term (starter incomplete).

use crate::input::model_schema::BridgeModel;
use crate::input::plan_schema::CalibrationPlan;

pub fn regularization_term(_model: &BridgeModel, _theta: &[f64], _plan: &CalibrationPlan) -> f64 {
    0.0
}
