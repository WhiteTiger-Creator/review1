use crate::types::{ChannelView, GateStatus, KitPolicy, RjCtx};

fn slot_present(view: &ChannelView, name: &str) -> bool {
    for (i, n) in view.names.iter().enumerate() {
        if n == name {
            return i < view.present.len() && view.present[i];
        }
    }
    false
}

fn required_list<'a>(ctx: &'a RjCtx, view: &ChannelView) -> &'a [String] {
    if view.names.iter().any(|n| n == "w_n") {
        &ctx.required2
    } else {
        &ctx.required0
    }
}

fn forbid_missing(view: &ChannelView, policy: &KitPolicy) -> bool {
    for name in &policy.forbid {
        if !slot_present(view, name) {
            return true;
        }
    }
    false
}

fn required_missing(ctx: &RjCtx, view: &ChannelView) -> bool {
    if view.names.is_empty() {
        return true;
    }
    for name in required_list(ctx, view) {
        if !slot_present(view, name) {
            return true;
        }
    }
    false
}

pub fn gz_p_gate(ctx: &RjCtx, view: &ChannelView, policy: &KitPolicy) -> GateStatus {
    if forbid_missing(view, policy) {
        return GateStatus::Reject;
    }
    if required_missing(ctx, view) {
        return GateStatus::Reject;
    }
    GateStatus::Accept
}
