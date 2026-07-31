use crate::types::{ChannelView, GateStatus, KitPolicy};

pub fn dial_gz_read(view: &ChannelView, policy: &KitPolicy) -> GateStatus {
    let _ = (view, policy);
    GateStatus::Accept
}
