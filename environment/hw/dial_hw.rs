use crate::types::{ChannelView, PredSeries};

pub fn dial_hw_dump(view: &ChannelView) -> PredSeries {
    let mut vals = Vec::new();
    let n = view.bytes.len() / 4;
    for i in 0..n.min(3) {
        let off = i * 4;
        let v = f32::from_le_bytes([
            view.bytes[off],
            view.bytes[off + 1],
            view.bytes[off + 2],
            view.bytes[off + 3],
        ]) as f64;
        vals.push(((i as u64) + 1, v));
    }
    PredSeries { vals }
}
