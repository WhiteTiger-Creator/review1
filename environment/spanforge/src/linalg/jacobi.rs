//! Symmetric Jacobi eigenanalysis for standard eigenproblems.

use crate::linalg::dense::{dot, Matrix};

#[derive(Clone, Debug)]
pub struct EigenDecomposition {
    pub eigenvalues: Vec<f64>,
    pub eigenvectors: Matrix,
}

pub fn jacobi_symmetric(a_in: &Matrix) -> Result<EigenDecomposition, String> {
    let n = a_in.n;
    let mut a = a_in.clone();
    let mut v = Matrix::zeros(n);
    for i in 0..n {
        v.set(i, i, 1.0);
    }
    let max_sweeps = 100 * n.max(1);
    for _ in 0..max_sweeps {
        let mut p = 0usize;
        let mut q = 1usize;
        let mut max_off = 0.0;
        for i in 0..n {
            for j in (i + 1)..n {
                let val = a.get(i, j).abs();
                if val > max_off {
                    max_off = val;
                    p = i;
                    q = j;
                }
            }
        }
        if max_off < 1e-15 {
            break;
        }
        let app = a.get(p, p);
        let aqq = a.get(q, q);
        let apq = a.get(p, q);
        let tau = (aqq - app) / (2.0 * apq);
        let t = if tau >= 0.0 {
            1.0 / (tau + (1.0 + tau * tau).sqrt())
        } else {
            -1.0 / (-tau + (1.0 + tau * tau).sqrt())
        };
        let c = 1.0 / (1.0 + t * t).sqrt();
        let s = t * c;
        for i in 0..n {
            if i != p && i != q {
                let aip = a.get(i, p);
                let aiq = a.get(i, q);
                a.set(i, p, c * aip - s * aiq);
                a.set(p, i, c * aip - s * aiq);
                a.set(i, q, s * aip + c * aiq);
                a.set(q, i, s * aip + c * aiq);
            }
        }
        a.set(p, p, app - t * apq);
        a.set(q, q, aqq + t * apq);
        a.set(p, q, 0.0);
        a.set(q, p, 0.0);
        for i in 0..n {
            let vip = v.get(i, p);
            let viq = v.get(i, q);
            v.set(i, p, c * vip - s * viq);
            v.set(i, q, s * vip + c * viq);
        }
    }
    let mut pairs: Vec<(f64, usize)> = (0..n).map(|i| (a.get(i, i), i)).collect();
    pairs.sort_by(|x, y| {
        x.0.partial_cmp(&y.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| x.1.cmp(&y.1))
    });
    let mut eigenvalues = Vec::with_capacity(n);
    let mut eigenvectors = Matrix::zeros(n);
    for (new_j, &(val, old_j)) in pairs.iter().enumerate() {
        if !val.is_finite() {
            return Err("non-finite eigenvalue".into());
        }
        eigenvalues.push(val);
        for i in 0..n {
            eigenvectors.set(i, new_j, v.get(i, old_j));
        }
        // Orthonormalize column against numerical drift
        let mut col: Vec<f64> = (0..n).map(|i| eigenvectors.get(i, new_j)).collect();
        let nrm = dot(&col, &col).sqrt();
        if nrm > 0.0 {
            for i in 0..n {
                col[i] /= nrm;
                eigenvectors.set(i, new_j, col[i]);
            }
        }
    }
    Ok(EigenDecomposition {
        eigenvalues,
        eigenvectors,
    })
}
