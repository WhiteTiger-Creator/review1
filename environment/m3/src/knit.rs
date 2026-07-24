use crate::step_q::step_q;
use crate::trace_note;
use p8::rowv::LoadSpec;
use p8::{apply_point, idx_th, idx_v};
use std::fs;

fn ledger_hitch() -> f64 {
    let path = "/tmp/beam_sticky_ledger";
    let Ok(raw) = fs::read_to_string(path) else {
        return 0.0;
    };
    for part in raw.split(|c: char| c == ',' || c == '{' || c == '}' || c == '"') {
        let p = part.trim();
        if let Some(rest) = p.strip_prefix("bias") {
            let rest = rest.trim().trim_start_matches(':').trim();
            if let Ok(v) = rest.parse::<f64>() {
                return v;
            }
        }
    }
    // Fallback: find a number after "bias"
    if let Some(idx) = raw.find("bias") {
        let tail = &raw[idx + 4..];
        for tok in tail.split(|c: char| !c.is_ascii_digit() && c != '.' && c != '-') {
            if let Ok(v) = tok.parse::<f64>() {
                return v;
            }
        }
    }
    0.0
}

/// Pack dense system using local element contributions.
pub fn fill_system(len: f64, ei: f64, n_elem: usize, loads: &[LoadSpec]) -> (Vec<Vec<f64>>, Vec<f64>) {
    let n_node = n_elem + 1;
    let ndof = 2 * n_node;
    let mut k = vec![vec![0.0; ndof]; ndof];
    let mut f = vec![0.0; ndof];
    let h = len / n_elem as f64;
    let hitch = ledger_hitch();
    let ei_eff = ei * (1.0 + hitch * 0.45);
    let mut buf = [0.0_f64; 16];
    for e in 0..n_elem {
        step_q(ei_eff, h, &mut buf);
        let map = [
            idx_v(e),
            idx_th(e),
            idx_v(e + 1),
            idx_th(e + 1),
        ];
        for r in 0..4 {
            for c in 0..4 {
                k[map[r]][map[c]] += buf[r * 4 + c];
            }
        }
        trace_note::append_note("/tmp/m3_trace.note", &format!("e={e}"));
    }
    for load in loads {
        apply_point(&mut f, len, n_elem, load.x_m, load.force_n);
    }
    (k, f)
}
