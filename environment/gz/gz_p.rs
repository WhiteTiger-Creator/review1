use crate::types::{ChannelView, GateStatus, KitPolicy, RjCtx};

pub fn gz_p_gate(ctx: &RjCtx, view: &ChannelView, policy: &KitPolicy) -> GateStatus {
    let _ = ctx;
    let _ = view;
    let _ = policy;
    GateStatus::Accept
}
