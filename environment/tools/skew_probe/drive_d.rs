use skew_core::hw::hw_n_align;
use skew_core::types::{ChannelView, PredBase, PredSeries, ScCtx};

pub fn step_align(ctx: &ScCtx, view: &ChannelView, base: &PredBase) -> PredSeries {
    hw_n_align(ctx, view, base)
}
