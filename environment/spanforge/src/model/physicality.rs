//! Mass and stiffness-box physicality checks.

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::model_schema::BridgeModel;
use crate::linalg::cholesky;
use crate::model::assembly::assemble_stiffness;

pub fn validate_mass(model: &BridgeModel) -> AppResult<cholesky::Cholesky> {
    cholesky::factorize(&model.mass).map_err(|e| (FailureCode::EMassPhysicality, e))
}

pub fn validate_stiffness_box(model: &BridgeModel) -> AppResult<()> {
    let g = model.groups.len();
    let corners = 1usize << g;
    for mask in 0..corners {
        let mut theta = vec![0.0; g];
        for i in 0..g {
            theta[i] = if (mask >> i) & 1 == 0 {
                model.groups[i].lower
            } else {
                model.groups[i].upper
            };
        }
        let k = assemble_stiffness(model, &theta);
        if let Err(e) = cholesky::factorize(&k) {
            return fail(
                FailureCode::EStiffnessBox,
                format!("nonphysical stiffness at corner mask {mask}: {e}"),
            );
        }
    }
    Ok(())
}
