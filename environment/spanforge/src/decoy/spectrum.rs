//! Complete spectrum decoy: validate model and emit modal spectrum JSON.

use crate::diagnostic::failure::AppResult;
use crate::input::model_schema::{load_model, BridgeModel};
use crate::linalg::dense::format_f64;
use crate::linalg::generalized;
use crate::modal::cluster::{cluster_by_values, cluster_ranges};
use crate::modal::mass_normalize::{apply_isolated_signs, mass_normalize};
use crate::model::assembly::{assemble_stiffness, initial_theta};
use crate::model::physicality::{validate_mass, validate_stiffness_box};
use std::path::Path;

pub fn run_spectrum(model_path: &Path) -> AppResult<()> {
    let model = load_model(model_path)?;
    let m_chol = validate_mass(&model)?;
    validate_stiffness_box(&model)?;
    let theta = initial_theta(&model);
    let k = assemble_stiffness(&model, &theta);
    let mut gm = generalized::solve_generalized(&k, &m_chol)
        .map_err(|e| (crate::diagnostic::failure::FailureCode::EEigensystem, e))?;
    mass_normalize(&mut gm.modes, &model.mass);
    // spectrum uses a fixed tiny cluster tolerance for reporting adjacent eigenvalues
    let tol = 1e-9;
    let clusters = cluster_by_values(&gm.eigenvalues, &gm.frequencies_hz, tol);
    apply_isolated_signs(&mut gm.modes, &cluster_ranges(&clusters));
    let json = render_spectrum(&model, &theta, &gm.eigenvalues, &gm.frequencies_hz, &clusters);
    print!("{json}");
    Ok(())
}

fn render_spectrum(
    model: &BridgeModel,
    theta: &[f64],
    eigenvalues: &[f64],
    frequencies: &[f64],
    clusters: &[crate::modal::cluster::Cluster],
) -> String {
    let mut out = String::from("{\n");
    out.push_str(&format!("  \"model_sha256\": \"{}\",\n", model.model_sha256));
    out.push_str(&format!("  \"dof_count\": {},\n", model.dofs.len()));
    out.push_str(&format!("  \"group_count\": {},\n", model.groups.len()));
    let th: Vec<String> = theta.iter().map(|v| format_f64(*v)).collect();
    out.push_str(&format!("  \"initial_group_values\": [{}],\n", th.join(", ")));
    out.push_str(&format!(
        "  \"positive_eigenvalue_count\": {},\n",
        eigenvalues.len()
    ));
    let freqs: Vec<String> = frequencies.iter().map(|v| format_f64(*v)).collect();
    out.push_str(&format!("  \"frequencies_hz\": [{}],\n", freqs.join(", ")));
    out.push_str("  \"clusters\": [\n");
    for (i, c) in clusters.iter().enumerate() {
        let ords: Vec<String> = c.member_indices.iter().map(|x| x.to_string()).collect();
        out.push_str("    {\n");
        out.push_str(&format!(
            "      \"ordinals\": [{}],\n",
            ords.join(", ")
        ));
        out.push_str(&format!(
            "      \"centroid_hz\": {}\n",
            format_f64(c.centroid_hz)
        ));
        out.push_str("    }");
        if i + 1 != clusters.len() {
            out.push(',');
        }
        out.push('\n');
    }
    out.push_str("  ]\n}\n");
    out
}
