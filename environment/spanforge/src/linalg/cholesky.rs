//! Cholesky factorization with documented absolute pivot floor.

use crate::linalg::dense::Matrix;

pub const PIVOT_FLOOR: f64 = 1e-14;

#[derive(Clone, Debug)]
pub struct Cholesky {
    pub n: usize,
    pub lower: Matrix,
}

pub fn factorize(a: &Matrix) -> Result<Cholesky, String> {
    let n = a.n;
    let mut l = Matrix::zeros(n);
    for i in 0..n {
        for j in 0..=i {
            let mut sum = a.get(i, j);
            for k in 0..j {
                sum -= l.get(i, k) * l.get(j, k);
            }
            if i == j {
                if sum <= PIVOT_FLOOR {
                    return Err(format!("nonpositive pivot at {i}: {sum}"));
                }
                l.set(i, j, sum.sqrt());
            } else {
                let diag = l.get(j, j);
                if diag <= PIVOT_FLOOR {
                    return Err(format!("invalid pivot during off-diagonal at {j}"));
                }
                l.set(i, j, sum / diag);
            }
        }
    }
    Ok(Cholesky { n, lower: l })
}

pub fn solve_lower(l: &Matrix, b: &[f64]) -> Vec<f64> {
    let n = l.n;
    let mut x = vec![0.0; n];
    for i in 0..n {
        let mut s = b[i];
        for j in 0..i {
            s -= l.get(i, j) * x[j];
        }
        x[i] = s / l.get(i, i);
    }
    x
}

pub fn solve_upper_from_lower(l: &Matrix, b: &[f64]) -> Vec<f64> {
    let n = l.n;
    let mut x = vec![0.0; n];
    for i in (0..n).rev() {
        let mut s = b[i];
        for j in (i + 1)..n {
            s -= l.get(j, i) * x[j];
        }
        x[i] = s / l.get(i, i);
    }
    x
}

pub fn solve(chol: &Cholesky, b: &[f64]) -> Vec<f64> {
    let y = solve_lower(&chol.lower, b);
    solve_upper_from_lower(&chol.lower, &y)
}
