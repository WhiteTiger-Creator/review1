use crate::types::{ChannelView, FillReport};

pub fn stub_fy_noop(view: &mut ChannelView) -> FillReport {
    let _ = view;
    FillReport { filled: 0 }
}
