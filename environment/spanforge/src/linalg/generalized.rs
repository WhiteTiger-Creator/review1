//! Generalized eigenproblem K phi = lambda M phi via Cholesky of M.

use crate::linalg::cholesky::{self, Cholesky};
use crate::linalg::dense::Matrix;
use crate::linalg::jacobi::{self, EigenDecomposition};

pub struct GeneralizedModes {
    pub eigenvalues: Vec<f64>,
    pub frequencies_hz: Vec<f64>,
    pub modes: Vec<Vec<f64>>,
}

pub fn solve_generalized(k: &Matrix, m_chol: &Cholesky) -> Result<GeneralizedModes, String> {
    let n = k.n;
    // Form A = L^{-1} K L^{-T}
    let mut a = Matrix::zeros(n);
    for j in 0..n {
        let mut e = vec![0.0; n];
        e[j] = 1.0;
        let lt_inv_e = cholesky::solve_upper_from_lower(&m_chol.lower, &e);
        let k_vec = k.mul_vec(&lt_inv_e);
        let a_col = cholesky::solve_lower(&m_chol.lower, &k_vec);
        for i in 0..n {
            a.set(i, j, a_col[i]);
        }
    }
    // Symmetrize A numerically
    let _ = a.symmetrize_checked().or_else(|_| {
        for i in 0..n {
            for j in (i + 1)..n {
                let mean = 0.5 * (a.get(i, j) + a.get(j, i));
                a.set(i, j, mean);
                a.set(j, i, mean);
            }
        }
        Ok::<(), String>(())
    });
    let EigenDecomposition {
        eigenvalues,
        eigenvectors,
    } = jacobi::jacobi_symmetric(&a)?;

    let mut kept_lambda = Vec::new();
    let mut kept_modes = Vec::new();
    for j in 0..n {
        let lambda = eigenvalues[j];
        if lambda.is_finite() && lambda > 0.0 {
            let mut y: Vec<f64> = (0..n).map(|i| eigenvectors.get(i, j)).collect();
            // phi = L^{-T} y
            let phi = cholesky::solve_upper_from_lower(&m_chol.lower, &y);
            kept_lambda.push(lambda);
            kept_modes.push(phi);
        }
    }
    if kept_lambda.is_empty() {
        return Err("no positive eigenvalues".into());
    }
    let frequencies_hz: Vec<f64> = kept_lambda
        .iter()
        .map(|l| l.sqrt() / (2.0 * std::f64::consts::PI))
        .collect();
    Ok(GeneralizedModes {
        eigenvalues: kept_lambda,
        frequencies_hz,
        modes: kept_modes,
    })
}
