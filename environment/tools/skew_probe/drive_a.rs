use skew_core::nx::nx_k_bind;
use skew_core::types::{AxCtx, ByteView, ChannelView};

pub fn step_bind(ctx: &AxCtx, src: &ByteView, gen: u32) -> ChannelView {
    nx_k_bind(ctx, src, gen)
}
