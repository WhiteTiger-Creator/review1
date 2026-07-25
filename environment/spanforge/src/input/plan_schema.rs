//! Calibration plan schema and canonical identity.

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::canonicalize::{render_f64, sha256_hex};
use crate::input::strict_json::{
    parse_object_with_code, reject_unknown, require_f64, require_string, require_usize,
};
use std::path::Path;

#[derive(Clone, Debug)]
pub struct CalibrationPlan {
    pub mode_count: usize,
    pub frequency_weight: f64,
    pub shape_weight: f64,
    pub regularization_weight: f64,
    pub cluster_relative_tolerance: f64,
    pub pairing_frequency_gate: f64,
    pub finite_difference_step: f64,
    pub gradient_tolerance: f64,
    pub step_tolerance: f64,
    pub objective_tolerance: f64,
    pub rank_tolerance: f64,
    pub max_iterations: usize,
    pub plan_sha256: String,
}

pub fn load_plan(path: &Path, measured_modes: usize, dof_count: usize) -> AppResult<CalibrationPlan> {
    let bytes = crate::input::strict_json::read_bytes(path)?;
    decode_plan(&bytes, measured_modes, dof_count)
}

pub fn decode_plan(bytes: &[u8], measured_modes: usize, dof_count: usize) -> AppResult<CalibrationPlan> {
    let code = FailureCode::EPlanSchema;
    let map = parse_object_with_code(bytes, code)?;
    reject_unknown(
        &map,
        &[
            "format",
            "mode_count",
            "frequency_weight",
            "shape_weight",
            "regularization_weight",
            "cluster_relative_tolerance",
            "pairing_frequency_gate",
            "finite_difference_step",
            "gradient_tolerance",
            "step_tolerance",
            "objective_tolerance",
            "rank_tolerance",
            "max_iterations",
        ],
        code,
    )?;
    let format = require_string(&map, "format", code)?;
    if format != "bridge-calibration-plan-v1" {
        return fail(code, "unsupported plan format");
    }
    let mode_count = require_usize(&map, "mode_count", code)?;
    if mode_count < measured_modes || mode_count > dof_count {
        return fail(code, "mode_count out of admissible range");
    }
    let frequency_weight = require_f64(&map, "frequency_weight", code)?;
    let shape_weight = require_f64(&map, "shape_weight", code)?;
    let regularization_weight = require_f64(&map, "regularization_weight", code)?;
    let cluster_relative_tolerance = require_f64(&map, "cluster_relative_tolerance", code)?;
    let pairing_frequency_gate = require_f64(&map, "pairing_frequency_gate", code)?;
    let finite_difference_step = require_f64(&map, "finite_difference_step", code)?;
    let gradient_tolerance = require_f64(&map, "gradient_tolerance", code)?;
    let step_tolerance = require_f64(&map, "step_tolerance", code)?;
    let objective_tolerance = require_f64(&map, "objective_tolerance", code)?;
    let rank_tolerance = require_f64(&map, "rank_tolerance", code)?;
    let max_iterations = require_usize(&map, "max_iterations", code)?;
    for (name, v) in [
        ("frequency_weight", frequency_weight),
        ("shape_weight", shape_weight),
        ("cluster_relative_tolerance", cluster_relative_tolerance),
        ("pairing_frequency_gate", pairing_frequency_gate),
        ("finite_difference_step", finite_difference_step),
        ("gradient_tolerance", gradient_tolerance),
        ("step_tolerance", step_tolerance),
        ("objective_tolerance", objective_tolerance),
        ("rank_tolerance", rank_tolerance),
    ] {
        if !(v > 0.0 && v.is_finite()) {
            return fail(code, format!("{name} must be positive finite"));
        }
    }
    if !(regularization_weight >= 0.0 && regularization_weight.is_finite()) {
        return fail(code, "regularization_weight must be nonnegative finite");
    }
    if !(4..=500).contains(&max_iterations) {
        return fail(code, "max_iterations out of range");
    }
    let plan = CalibrationPlan {
        mode_count,
        frequency_weight,
        shape_weight,
        regularization_weight,
        cluster_relative_tolerance,
        pairing_frequency_gate,
        finite_difference_step,
        gradient_tolerance,
        step_tolerance,
        objective_tolerance,
        rank_tolerance,
        max_iterations,
        plan_sha256: String::new(),
    };
    let raw = render_canonical_plan(&plan);
    let mut plan = plan;
    plan.plan_sha256 = sha256_hex(raw.as_bytes());
    Ok(plan)
}

fn render_canonical_plan(p: &CalibrationPlan) -> String {
    format!(
        "{{\n  \"format\": \"bridge-calibration-plan-v1\",\n  \"mode_count\": {},\n  \"frequency_weight\": {},\n  \"shape_weight\": {},\n  \"regularization_weight\": {},\n  \"cluster_relative_tolerance\": {},\n  \"pairing_frequency_gate\": {},\n  \"finite_difference_step\": {},\n  \"gradient_tolerance\": {},\n  \"step_tolerance\": {},\n  \"objective_tolerance\": {},\n  \"rank_tolerance\": {},\n  \"max_iterations\": {}\n}}\n",
        p.mode_count,
        render_f64(p.frequency_weight),
        render_f64(p.shape_weight),
        render_f64(p.regularization_weight),
        render_f64(p.cluster_relative_tolerance),
        render_f64(p.pairing_frequency_gate),
        render_f64(p.finite_difference_step),
        render_f64(p.gradient_tolerance),
        render_f64(p.step_tolerance),
        render_f64(p.objective_tolerance),
        render_f64(p.rank_tolerance),
        p.max_iterations
    )
}
