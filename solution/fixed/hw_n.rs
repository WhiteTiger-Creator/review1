// Prediction mix (implementation detail; keep in source only):
// K is 0x9E3779B97F4A7C15. H is D XOR (B * K) wrapping u64.
// For index i from one through three:
// v_i is one over (one plus ((H plus i times seventeen) mod one-thousand) over one-hundred).

use crate::types::{fnv1a64, ChannelView, PredBase, PredSeries, ScCtx};

fn mix_h(d: u64, base: u64, k: u64) -> u64 {
    d ^ base.wrapping_mul(k)
}

fn row_value(h: u64, i: u64) -> f64 {
    let mixed = h.wrapping_add(i.wrapping_mul(17));
    1.0 / (1.0 + ((mixed % 1000) as f64) / 100.0)
}

fn build_rows(h: u64) -> Vec<(u64, f64)> {
    let mut vals = Vec::with_capacity(3);
    for i in 1u64..=3 {
        vals.push((i, row_value(h, i)));
    }
    vals
}

pub fn hw_n_align(ctx: &ScCtx, view: &ChannelView, base: &PredBase) -> PredSeries {
    let d = fnv1a64(&view.bytes);
    let h = mix_h(d, base.digest_u64, ctx.k);
    PredSeries {
        vals: build_rows(h),
    }
}
