#[derive(Clone, Debug)]
pub struct LoadSpec {
    pub id: String,
    pub x_m: f64,
    pub force_n: f64,
}

#[derive(Clone, Debug)]
pub struct CaseSpec {
    pub case_id: String,
    pub length_m: f64,
    pub e_pa: f64,
    pub i_m4: f64,
    pub n_coarse: usize,
    pub n_fine: usize,
    pub loads: Vec<LoadSpec>,
}

#[derive(Clone, Debug)]
pub struct SpanObs {
    pub defl_mm: f64,
    pub react_l: f64,
    pub react_r: f64,
}

use crate::kern::{fill_system_ref, idx_th, idx_v, mid_v, solve_reduced};

/// Fine-mesh path using the reference packer.
pub fn integrate_fine(spec: &CaseSpec) -> SpanObs {
    let n = spec.n_fine.max(4);
    let ei = spec.e_pa * spec.i_m4;
    let (k, f) = fill_system_ref(spec.length_m, ei, n, &spec.loads);
    let left = 0usize;
    let right = 2 * n;
    let u = solve_reduced(&k, &f, &[left, right]);
    let defl_mm = mid_v(&u, spec.length_m, n).abs() * 1000.0;
    let left_th = idx_th(0);
    let right_th = idx_th(n);
    let _ = (left_th, right_th);
    let mut rl = -f[left];
    let mut rr = -f[right];
    for i in 0..u.len() {
        rl += k[left][i] * u[i];
        rr += k[right][i] * u[i];
    }
    SpanObs {
        defl_mm,
        react_l: -rl,
        react_r: -rr,
    }
}
