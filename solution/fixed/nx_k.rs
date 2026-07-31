use crate::types::{AxCtx, ByteView, ChannelView};

fn put_f32(out: &mut Vec<u8>, v: f32) {
    out.extend_from_slice(&v.to_le_bytes());
}

fn map_pairs_for<'a>(ctx: &'a AxCtx, gen: u32) -> Option<&'a [(String, String)]> {
    for (g, pairs) in &ctx.maps {
        if *g == gen {
            return Some(pairs.as_slice());
        }
    }
    None
}

fn canon_for(ctx: &AxCtx, gen: u32) -> &[String] {
    if gen >= 2 && gen != 3 {
        &ctx.canon2
    } else {
        &ctx.canon0
    }
}

fn resolve_one(ctx: &AxCtx, gen: u32, wire: &str) -> Option<String> {
    let canon = canon_for(ctx, gen);
    if let Some(pairs) = map_pairs_for(ctx, gen) {
        for (w, c) in pairs {
            if w == wire {
                return Some(c.clone());
            }
        }
        for (_, c) in pairs {
            if c == wire {
                return Some(wire.to_string());
            }
        }
        for n in canon {
            if n == wire {
                return Some(wire.to_string());
            }
        }
        return None;
    }
    for n in canon {
        if n == wire {
            return Some(wire.to_string());
        }
    }
    None
}

fn collect_resolved(ctx: &AxCtx, gen: u32) -> Option<Vec<(String, f32)>> {
    let mut out = Vec::with_capacity(ctx.wire.len());
    for (w, v) in &ctx.wire {
        match resolve_one(ctx, gen, w) {
            Some(c) => {
                if let Some((_, prev)) = out.iter_mut().find(|(n, _)| n == &c) {
                    *prev = *v;
                } else {
                    out.push((c, *v));
                }
            }
            None => return None,
        }
    }
    Some(out)
}

fn materialize(canon: &[String], resolved: &[(String, f32)]) -> ChannelView {
    let mut bytes = Vec::with_capacity(canon.len() * 4);
    let mut present = Vec::with_capacity(canon.len());
    let mut names = Vec::with_capacity(canon.len());
    for slot in canon {
        names.push(slot.clone());
        match resolved.iter().find(|(n, _)| n == slot) {
            Some((_, v)) => {
                put_f32(&mut bytes, *v);
                present.push(true);
            }
            None => {
                put_f32(&mut bytes, 0.0);
                present.push(false);
            }
        }
    }
    ChannelView {
        bytes,
        names,
        present,
    }
}

pub fn nx_k_bind(ctx: &AxCtx, src: &ByteView, gen: u32) -> ChannelView {
    let _ = src;
    let canon = canon_for(ctx, gen).to_vec();
    match collect_resolved(ctx, gen) {
        Some(resolved) => materialize(&canon, &resolved),
        None => ChannelView::default(),
    }
}
