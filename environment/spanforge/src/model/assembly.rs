//! Affine stiffness assembly K(theta).

use crate::input::model_schema::BridgeModel;
use crate::linalg::dense::Matrix;

pub fn assemble_stiffness(model: &BridgeModel, theta: &[f64]) -> Matrix {
    assert_eq!(theta.len(), model.groups.len());
    let mut k = model.fixed_stiffness.clone();
    for (g, &t) in model.groups.iter().zip(theta.iter()) {
        k.add_scaled(&g.contribution, t);
    }
    k
}

pub fn initial_theta(model: &BridgeModel) -> Vec<f64> {
    model.groups.iter().map(|g| g.initial).collect()
}

pub fn reference_theta(model: &BridgeModel) -> Vec<f64> {
    model.groups.iter().map(|g| g.reference).collect()
}

pub fn lower_bounds(model: &BridgeModel) -> Vec<f64> {
    model.groups.iter().map(|g| g.lower).collect()
}

pub fn upper_bounds(model: &BridgeModel) -> Vec<f64> {
    model.groups.iter().map(|g| g.upper).collect()
}
