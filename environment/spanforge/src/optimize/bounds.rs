//! Parameter bounds helpers (partial starter).

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BoundState {
    Lower,
    Upper,
    Free,
}

impl BoundState {
    pub fn as_str(self) -> &'static str {
        match self {
            BoundState::Lower => "LOWER",
            BoundState::Upper => "UPPER",
            BoundState::Free => "FREE",
        }
    }
}

pub fn project(theta: &mut [f64], lower: &[f64], upper: &[f64]) {
    for i in 0..theta.len() {
        if theta[i] < lower[i] {
            theta[i] = lower[i];
        }
        if theta[i] > upper[i] {
            theta[i] = upper[i];
        }
    }
}

pub fn classify(theta: f64, lower: f64, upper: f64) -> BoundState {
    if (theta - lower).abs() <= 1e-8 * lower.abs().max(1.0) {
        BoundState::Lower
    } else if (theta - upper).abs() <= 1e-8 * upper.abs().max(1.0) {
        BoundState::Upper
    } else {
        BoundState::Free
    }
}

pub fn project_gradient(grad: &[f64], _theta: &[f64], _lower: &[f64], _upper: &[f64]) -> Vec<f64> {
    grad.to_vec()
}

pub fn inf_norm(v: &[f64]) -> f64 {
    v.iter().fold(0.0_f64, |a, &b| a.max(b.abs()))
}
