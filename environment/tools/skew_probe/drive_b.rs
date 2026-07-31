use skew_core::fy::fy_m_fill;
use skew_core::types::{ChannelView, DvCtx, FillReport, PathKind};

pub fn step_fill(ctx: &DvCtx, view: &mut ChannelView, path: PathKind) -> FillReport {
    fy_m_fill(ctx, view, path)
}
