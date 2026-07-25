//! Mass-normalize eigenvectors and apply isolated-mode sign convention.

use crate::linalg::dense::Matrix;

pub fn mass_normalize(modes: &mut [Vec<f64>], mass: &Matrix) {
    for phi in modes.iter_mut() {
        let q = mass.quadratic(phi);
        if q > 0.0 {
            let s = q.sqrt();
            for v in phi.iter_mut() {
                *v /= s;
            }
        }
    }
}

pub fn apply_isolated_signs(modes: &mut [Vec<f64>], cluster_ranges: &[(usize, usize)]) {
    for &(start, end) in cluster_ranges {
        if end - start == 1 {
            let phi = &mut modes[start];
            for v in phi.iter() {
                if v.abs() > 1e-14 {
                    if *v < 0.0 {
                        for x in phi.iter_mut() {
                            *x = -*x;
                        }
                    }
                    break;
                }
            }
        }
    }
}
