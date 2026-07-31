use crate::types::{ChannelView, DvCtx, FillReport, PathKind};

fn set_slot(view: &mut ChannelView, idx: usize, v: f32) {
    let off = idx * 4;
    if off + 4 > view.bytes.len() {
        view.bytes.resize(off + 4, 0);
    }
    let b = v.to_le_bytes();
    view.bytes[off..off + 4].copy_from_slice(&b);
    if idx >= view.present.len() {
        view.present.resize(idx + 1, false);
    }
    view.present[idx] = true;
}

fn lookup_fill(ctx: &DvCtx, name: &str) -> Option<f32> {
    for (n, v) in &ctx.fills {
        if n == name {
            return Some(*v);
        }
    }
    None
}

fn missing_indices(view: &ChannelView) -> Vec<usize> {
    let mut out = Vec::new();
    for i in 0..view.names.len() {
        if i >= view.present.len() || !view.present[i] {
            out.push(i);
        }
    }
    out
}

pub fn fy_m_fill(ctx: &DvCtx, view: &mut ChannelView, path: PathKind) -> FillReport {
    let _ = path;
    let names = view.names.clone();
    let mut filled = 0usize;
    for i in missing_indices(view) {
        let name = &names[i];
        if let Some(val) = lookup_fill(ctx, name) {
            set_slot(view, i, val);
            filled += 1;
        }
    }
    FillReport { filled }
}
