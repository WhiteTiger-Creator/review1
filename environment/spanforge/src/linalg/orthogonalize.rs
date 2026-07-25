//! Deterministic modified Gram-Schmidt orthonormalization.

use crate::linalg::dense::{dot, norm2, scale_inplace};

pub fn modified_gram_schmidt(columns: &[Vec<f64>]) -> Vec<Vec<f64>> {
    let mut basis: Vec<Vec<f64>> = Vec::new();
    for col in columns {
        let mut v = col.clone();
        for b in &basis {
            let proj = dot(&v, b);
            for i in 0..v.len() {
                v[i] -= proj * b[i];
            }
        }
        let nrm = norm2(&v);
        if nrm <= 1e-12 {
            continue;
        }
        scale_inplace(&mut v, 1.0 / nrm);
        basis.push(v);
    }
    basis
}

pub fn frobenius_inner_sq(u: &[Vec<f64>], v: &[Vec<f64>]) -> f64 {
    // || U^T V ||_F^2
    let mut s = 0.0;
    for ui in u {
        for vj in v {
            let d = dot(ui, vj);
            s += d * d;
        }
    }
    s
}
