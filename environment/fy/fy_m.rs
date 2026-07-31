use crate::types::{ChannelView, DvCtx, FillReport, PathKind};

pub fn fy_m_fill(ctx: &DvCtx, view: &mut ChannelView, path: PathKind) -> FillReport {
    let mut filled = 0usize;
    let names = view.names.clone();
    for (i, name) in names.iter().enumerate() {
        let need = i >= view.present.len() || !view.present[i];
        if !need {
            continue;
        }
        let mut val = 0.0f32;
        if path == PathKind::Off {
            for (n, v) in &ctx.fills {
                if n == name {
                    val = *v;
                    break;
                }
            }
        }
        let off = i * 4;
        if off + 4 > view.bytes.len() {
            view.bytes.resize(off + 4, 0);
        }
        let b = val.to_le_bytes();
        view.bytes[off..off + 4].copy_from_slice(&b);
        if i >= view.present.len() {
            view.present.resize(i + 1, false);
        }
        view.present[i] = true;
        filled += 1;
    }
    FillReport { filled }
}
