use skew_core::gz::gz_p_gate;
use skew_core::types::{ChannelView, GateStatus, KitPolicy, RjCtx};

pub fn step_gate(ctx: &RjCtx, view: &ChannelView, policy: &KitPolicy) -> GateStatus {
    gz_p_gate(ctx, view, policy)
}
