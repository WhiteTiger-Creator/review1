use std::fs;
use std::path::{Path, PathBuf};

use crate::drive_a;
use crate::drive_b;
use crate::drive_c;
use crate::drive_d;
use skew_core::fy::stub_fy_noop;
use skew_core::nx::legacy_nx_copy;
use skew_core::types::*;

pub struct KitRev {
    pub id: String,
    pub gen: u32,
    pub case: String,
}

pub struct Kit {
    pub seed: u64,
    pub forbid: Vec<String>,
    pub revs: Vec<KitRev>,
}

pub struct Slot {
    pub name: String,
    pub v: f32,
}

fn parse_string_value(s: &str) -> String {
    s.trim().trim_matches('"').to_string()
}

pub fn load_kit(path: &Path) -> Kit {
    let text = fs::read_to_string(path).expect("catalog");
    let mut seed = 0u64;
    let mut forbid = Vec::new();
    let mut revs = Vec::new();
    let mut cur_id = String::new();
    let mut cur_gen = 0u32;
    let mut cur_case = String::new();
    let mut in_rev = false;
    let mut in_forbid = false;

    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if line.starts_with("seed") {
            let p: Vec<&str> = line.split('=').collect();
            if p.len() == 2 {
                seed = p[1].trim().parse().unwrap_or(0);
            }
            continue;
        }
        if line.starts_with("forbid_drop") {
            in_forbid = true;
            let rest = line.split('=').nth(1).unwrap_or("").trim();
            if rest.starts_with('[') {
                let inner = rest.trim_matches(|c| c == '[' || c == ']');
                for part in inner.split(',') {
                    let t = parse_string_value(part.trim());
                    if !t.is_empty() {
                        forbid.push(t);
                    }
                }
                in_forbid = false;
            }
            continue;
        }
        if in_forbid {
            if line.starts_with(']') {
                in_forbid = false;
                continue;
            }
            let t = parse_string_value(line.trim_matches(','));
            if !t.is_empty() {
                forbid.push(t);
            }
            continue;
        }
        if line.starts_with("[[schema_revs]]") {
            if in_rev && !cur_id.is_empty() {
                revs.push(KitRev {
                    id: cur_id.clone(),
                    gen: cur_gen,
                    case: cur_case.clone(),
                });
            }
            in_rev = true;
            cur_id.clear();
            cur_gen = 0;
            cur_case.clear();
            continue;
        }
        if !in_rev {
            continue;
        }
        if let Some(rest) = line.strip_prefix("id") {
            let v = rest.trim().trim_start_matches('=').trim();
            cur_id = parse_string_value(v);
        } else if let Some(rest) = line.strip_prefix("gen") {
            let v = rest.trim().trim_start_matches('=').trim();
            cur_gen = v.parse().unwrap_or(0);
        } else if let Some(rest) = line.strip_prefix("case") {
            let v = rest.trim().trim_start_matches('=').trim();
            cur_case = parse_string_value(v);
        }
    }
    if in_rev && !cur_id.is_empty() {
        revs.push(KitRev {
            id: cur_id,
            gen: cur_gen,
            case: cur_case,
        });
    }
    Kit { seed, forbid, revs }
}

pub fn load_case(root: &Path, rel: &str) -> Vec<Slot> {
    let text = fs::read_to_string(root.join(rel)).expect("case");
    let mut slots = Vec::new();
    let mut name = String::new();
    for raw in text.lines() {
        let line = raw.trim().trim_end_matches(',');
        if let Some(rest) = line.strip_prefix("\"name\"") {
            let v = rest.trim().trim_start_matches(':').trim();
            name = parse_string_value(v);
        } else if let Some(rest) = line.strip_prefix("\"v\"") {
            let v = rest.trim().trim_start_matches(':').trim();
            let num: f32 = v.parse().unwrap_or(0.0);
            if !name.is_empty() {
                slots.push(Slot {
                    name: name.clone(),
                    v: num,
                });
                name.clear();
            }
        }
    }
    slots
}

pub fn make_ax_ctx() -> AxCtx {
    AxCtx {
        maps: vec![
            (
                1,
                vec![
                    ("v_a".into(), "u_a".into()),
                    ("v_c".into(), "u_c".into()),
                    ("u_b".into(), "u_b".into()),
                    ("u_d".into(), "u_d".into()),
                ],
            ),
            (
                0,
                vec![
                    ("u_a".into(), "u_a".into()),
                    ("u_b".into(), "u_b".into()),
                    ("u_c".into(), "u_c".into()),
                    ("u_d".into(), "u_d".into()),
                ],
            ),
            (
                2,
                vec![
                    ("u_a".into(), "u_a".into()),
                    ("u_b".into(), "u_b".into()),
                    ("w_n".into(), "w_n".into()),
                    ("u_c".into(), "u_c".into()),
                    ("u_d".into(), "u_d".into()),
                ],
            ),
            (
                3,
                vec![
                    ("u_a".into(), "u_a".into()),
                    ("u_b".into(), "u_b".into()),
                    ("u_d".into(), "u_d".into()),
                ],
            ),
        ],
        canon0: vec!["u_a".into(), "u_b".into(), "u_c".into(), "u_d".into()],
        canon2: vec![
            "u_a".into(),
            "u_b".into(),
            "w_n".into(),
            "u_c".into(),
            "u_d".into(),
        ],
        wire: Vec::new(),
    }
}

pub fn make_dv_ctx() -> DvCtx {
    DvCtx {
        fills: vec![("w_n".into(), 0.125)],
    }
}

pub fn make_rj_ctx() -> RjCtx {
    RjCtx {
        required0: vec!["u_a".into(), "u_b".into(), "u_c".into(), "u_d".into()],
        required2: vec![
            "u_a".into(),
            "u_b".into(),
            "w_n".into(),
            "u_c".into(),
            "u_d".into(),
        ],
    }
}

fn run_path(
    ax: &mut AxCtx,
    dv: &DvCtx,
    slots: &[Slot],
    gen: u32,
    path: PathKind,
) -> ChannelView {
    ax.wire = slots.iter().map(|s| (s.name.clone(), s.v)).collect();
    let empty = ByteView { data: &[] };
    let mut view = drive_a::step_bind(ax, &empty, gen);
    let _ = drive_b::step_fill(dv, &mut view, path);
    view
}

fn digest_of(view: &ChannelView) -> String {
    hex16(fnv1a64(&view.bytes))
}

fn baseline_digest(ax: &mut AxCtx, dv: &DvCtx, slots: &[Slot]) -> u64 {
    let mut base_slots = Vec::new();
    for s in slots {
        let mut n = s.name.clone();
        if n == "v_a" {
            n = "u_a".into();
        } else if n == "v_c" {
            n = "u_c".into();
        }
        if n == "w_n" {
            continue;
        }
        base_slots.push(Slot { name: n, v: s.v });
    }
    let view = run_path(ax, dv, &base_slots, 0, PathKind::Off);
    fnv1a64(&view.bytes)
}

pub struct TraceObj {
    pub rev_id: String,
    pub gen: u32,
    pub offline_geom: String,
    pub online_geom: String,
    pub chan_digest: String,
    pub gate_code: i32,
    pub pred_rows: Vec<(u64, f64)>,
}

pub fn eval_rev(root: &Path, kit: &Kit, rev: &KitRev) -> TraceObj {
    let slots = load_case(root, &rev.case);
    let mut ax = make_ax_ctx();
    let dv = make_dv_ctx();
    let rj = make_rj_ctx();
    let sc = ScCtx {
        k: 0x9E3779B97F4A7C15,
    };
    let policy = KitPolicy {
        forbid: kit.forbid.clone(),
    };

    let off = run_path(&mut ax, &dv, &slots, rev.gen, PathKind::Off);
    let on = run_path(&mut ax, &dv, &slots, rev.gen, PathKind::On);

    let status = drive_c::step_gate(&rj, &off, &policy);
    if status == GateStatus::Reject {
        return TraceObj {
            rev_id: rev.id.clone(),
            gen: rev.gen,
            offline_geom: String::new(),
            online_geom: String::new(),
            chan_digest: String::new(),
            gate_code: 2,
            pred_rows: Vec::new(),
        };
    }

    let base_u = baseline_digest(&mut ax, &dv, &slots);
    let pred = drive_d::step_align(
        &sc,
        &off,
        &PredBase {
            digest_u64: base_u,
            gen: 0,
        },
    );

    TraceObj {
        rev_id: rev.id.clone(),
        gen: rev.gen,
        offline_geom: digest_of(&off),
        online_geom: digest_of(&on),
        chan_digest: digest_of(&off),
        gate_code: 0,
        pred_rows: pred.vals,
    }
}

pub fn write_local_chk(root: &Path, out_dir: &Path) {
    let _ = fs::create_dir_all(out_dir);
    let mut ax = make_ax_ctx();
    let slots = load_case(root, "fixtures/revs/base.json");
    ax.wire = slots.iter().map(|s| (s.name.clone(), s.v)).collect();
    let raw: Vec<u8> = slots
        .iter()
        .flat_map(|s| s.v.to_le_bytes())
        .collect();
    let bv = ByteView { data: &raw };
    let mut view = legacy_nx_copy(&bv, &ax.canon0);
    let _ = stub_fy_noop(&mut view);
    let _ = fs::write(out_dir.join("same_gen.txt"), digest_of(&view));
}

pub fn emit_json(traces: &[TraceObj], edges: &[TraceObj], replay: &[(u64, f64)]) -> String {
    let mut s = String::from("{\n  \"rev_traces\": [\n");
    for (i, t) in traces.iter().enumerate() {
        s.push_str(&fmt_trace(t));
        if i + 1 != traces.len() {
            s.push(',');
        }
        s.push('\n');
    }
    s.push_str("  ],\n  \"edge_traces\": [\n");
    for (i, t) in edges.iter().enumerate() {
        s.push_str(&fmt_trace(t));
        if i + 1 != edges.len() {
            s.push(',');
        }
        s.push('\n');
    }
    s.push_str("  ],\n  \"replay_rows\": [");
    for (i, (t, v)) in replay.iter().enumerate() {
        if i > 0 {
            s.push(',');
        }
        s.push_str(&format!("{{\"t\":{},\"v\":{}}}", t, v));
    }
    s.push_str("]\n}\n");
    s
}

fn fmt_trace(t: &TraceObj) -> String {
    let mut preds = String::from("[");
    for (i, (tt, v)) in t.pred_rows.iter().enumerate() {
        if i > 0 {
            preds.push(',');
        }
        preds.push_str(&format!("{{\"t\":{},\"v\":{}}}", tt, v));
    }
    preds.push(']');
    format!(
        "    {{\"rev_id\":\"{}\",\"gen\":{},\"offline_geom\":\"{}\",\"online_geom\":\"{}\",\"chan_digest\":\"{}\",\"gate_code\":{},\"pred_rows\":{}}}",
        t.rev_id, t.gen, t.offline_geom, t.online_geom, t.chan_digest, t.gate_code, preds
    )
}

pub fn run_all(root: &Path, kit_path: &Path, journal_out: &Path) {
    let kit = load_kit(kit_path);
    let _seed = kit.seed;
    write_local_chk(root, Path::new("/app/output/local_chk"));

    let mut traces = Vec::new();
    for rev in &kit.revs {
        traces.push(eval_rev(root, &kit, rev));
    }

    let edge_specs = [
        ("edge_empty", 0u32, "fixtures/edges/empty.json"),
        ("edge_reorder", 0u32, "fixtures/edges/reorder.json"),
        ("edge_mixed", 1u32, "fixtures/edges/mixed.json"),
    ];
    let mut edges = Vec::new();
    for (id, gen, case) in edge_specs {
        let rev = KitRev {
            id: id.into(),
            gen,
            case: case.into(),
        };
        edges.push(eval_rev(root, &kit, &rev));
    }

    let mut replay = Vec::new();
    if let Some(first_ok) = traces.iter().find(|t| t.gate_code == 0) {
        let rev = kit
            .revs
            .iter()
            .find(|a| a.id == first_ok.rev_id)
            .expect("rev");
        let again = eval_rev(root, &kit, rev);
        replay = again.pred_rows.clone();
    }

    if let Some(parent) = journal_out.parent() {
        let _ = fs::create_dir_all(parent);
    }
    fs::write(journal_out, emit_json(&traces, &edges, &replay)).expect("write journal");
    let _ = PathBuf::from(".");
}
