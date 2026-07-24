pub mod knit;
pub mod step_q;
pub mod fold_r;
pub mod trace_note;

use knit::fill_system;
use fold_r::fold_r;
use p8::rowv::{CaseSpec, LoadSpec, SpanObs};
use p8::{idx_th, mid_v, solve_reduced};

/// Coarse-mesh span observables via local helpers.
pub fn integrate_coarse(spec: &CaseSpec) -> SpanObs {
    let n = spec.n_coarse.max(2);
    let (k, f) = fill_system(spec.length_m, spec.e_pa * spec.i_m4, n, &spec.loads);
    let left = 0usize;
    let right = 2 * n;
    let left_th = idx_th(0);
    let right_th = idx_th(n);
    let u = solve_reduced(&k, &f, &[left, right]);
    let defl_mm = mid_v(&u, spec.length_m, n).abs() * 1000.0;
    let yl = k[left].clone();
    let yr = k[right].clone();
    let tl = k[left_th].clone();
    let tr = k[right_th].clone();
    let (rl, rr) = fold_r(&u, &yl, &yr, &tl, &tr, f[left], f[right]);
    SpanObs {
        defl_mm,
        react_l: -rl,
        react_r: -rr,
    }
}

pub fn with_scaled_loads(spec: &CaseSpec, scaled: &[LoadSpec]) -> CaseSpec {
    let mut out = spec.clone();
    out.loads = scaled.to_vec();
    out
}

pub fn apply_hitch(loads: &[LoadSpec], hitch: f64) -> Vec<LoadSpec> {
    loads
        .iter()
        .map(|x| LoadSpec {
            id: x.id.clone(),
            x_m: x.x_m,
            force_n: x.force_n * (1.0 + hitch),
        })
        .collect()
}
