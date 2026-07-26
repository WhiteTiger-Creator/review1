//! Canonical MCR byte rendering.

use crate::linalg::dense::format_f64;
use crate::report::calibration_record::CalibrationRecord;

pub fn render_mcr(rec: &CalibrationRecord) -> String {
    let mut lines = Vec::new();
    lines.push("MCR 1".into());
    lines.push("STATUS CALIBRATED".into());
    lines.push(format!("MODEL_SHA256 {}", rec.model_sha256));
    lines.push(format!("SURVEY_SHA256 {}", rec.survey_sha256));
    lines.push(format!("PLAN_SHA256 {}", rec.plan_sha256));
    lines.push(format!(
        "OBJECTIVE {} {} {}",
        format_f64(rec.total),
        format_f64(rec.modal),
        format_f64(rec.regularization)
    ));
    lines.push(format!("ITERATIONS {}", rec.iterations));
    lines.push(format!(
        "PROJECTED_GRADIENT_INF {}",
        format_f64(rec.projected_gradient_inf)
    ));
    lines.push(format!("FINAL_STEP_INF {}", format_f64(rec.final_step_inf)));
    lines.push(format!(
        "NUMERICAL_RANK {} {}",
        rec.numerical_rank, rec.group_count
    ));
    lines.push(format!("CONFIDENCE {}", rec.confidence.as_str()));
    for g in &rec.groups {
        lines.push(format!(
            "GROUP {} {} {} {} {} {} {} {} {}",
            g.group_id,
            format_f64(g.theta),
            format_f64(g.lower),
            format_f64(g.upper),
            format_f64(g.reference),
            g.bound_state.as_str(),
            g.group_confidence,
            format_f64(g.sensitivity_score),
            g.sensitivity_rank
        ));
    }
    for p in &rec.assignment.pairs {
        lines.push(format!(
            "PAIR {} {} {} {} {} {} {}",
            p.measured_ids_csv,
            p.predicted_ordinals_csv,
            format_f64(p.measured_centroid_hz),
            format_f64(p.predicted_centroid_hz),
            format_f64(p.frequency_residual),
            format_f64(p.subspace_mac),
            format_f64(p.pair_cost)
        ));
    }
    lines.push("END".into());
    let mut out = lines.join("\n");
    out.push('\n');
    out
}
