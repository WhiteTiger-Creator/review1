use crate::types::{AxCtx, ByteView, ChannelView};

pub fn nx_k_bind(ctx: &AxCtx, src: &ByteView, gen: u32) -> ChannelView {
    let _ = src;
    let canon = if gen >= 2 && gen != 3 {
        ctx.canon2.clone()
    } else {
        ctx.canon0.clone()
    };
    let mut bytes = Vec::new();
    let mut present = Vec::new();
    let mut names = Vec::new();

    for slot in &canon {
        names.push(slot.clone());
        if let Some((_, v)) = ctx.wire.iter().find(|(n, _)| n == slot) {
            bytes.extend_from_slice(&v.to_le_bytes());
            present.push(true);
        } else {
            bytes.extend_from_slice(&0.0f32.to_le_bytes());
            present.push(false);
        }
    }
    ChannelView {
        bytes,
        names,
        present,
    }
}
