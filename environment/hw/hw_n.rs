// Prediction mix (implementation detail; keep in source only):
// K is 0x9E3779B97F4A7C15. H is D XOR (B * K) wrapping u64.
// For index i from one through three:
// v_i is one over (one plus ((H plus i times seventeen) mod one-thousand) over one-hundred).

use crate::types::{fnv1a64, ChannelView, PredBase, PredSeries, ScCtx};

pub fn hw_n_align(ctx: &ScCtx, view: &ChannelView, base: &PredBase) -> PredSeries {
    let _ = (ctx, base);
    let d = fnv1a64(&view.bytes);
    let mut vals = Vec::new();
    for i in 1u64..=3 {
        let h = d.wrapping_add(i.wrapping_mul(17));
        let v = 1.0 / (1.0 + ((h % 1000) as f64) / 100.0);
        vals.push((i, v));
    }
    PredSeries { vals }
}
