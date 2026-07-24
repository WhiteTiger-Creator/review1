mod outw;

use m3::{apply_hitch, integrate_coarse, with_scaled_loads};
use p8::integrate_fine;
use p8::rowv::{CaseSpec, LoadSpec};
use serde::Deserialize;
use serde_json::{json, Value};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

#[derive(Debug, Deserialize)]
struct LoadIn {
    id: String,
    x_m: f64,
    force_n: f64,
}

#[derive(Debug, Deserialize)]
struct CaseFile {
    case_id: String,
    length_m: f64,
    e_pa: f64,
    i_m4: f64,
    n_coarse: usize,
    n_fine: usize,
    loads: Vec<LoadIn>,
}

#[derive(Debug, Deserialize)]
struct ScaleRow {
    id: String,
    force: f64,
    aux_a: f64,
    aux_b: f64,
}

fn read_policy(root: &Path) -> (String, f64, f64, f64) {
    let text = fs::read_to_string(root.join("docs/tol_policy.md")).unwrap();
    let mut tol_class = "abs_span".to_string();
    let mut tol_limit = 0.50;
    let mut react_tol = 40.0;
    let mut lin_tol = 0.08;
    for line in text.lines() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("tol_class ") {
            tol_class = rest.trim().to_string();
        } else if let Some(rest) = line.strip_prefix("tol_limit ") {
            tol_limit = rest.trim().parse().unwrap_or(0.50);
        } else if let Some(rest) = line.strip_prefix("react_tol_limit ") {
            react_tol = rest.trim().parse().unwrap_or(40.0);
        } else if let Some(rest) = line.strip_prefix("lin_tol_limit ") {
            lin_tol = rest.trim().parse().unwrap_or(0.08);
        }
    }
    (tol_class, tol_limit, react_tol, lin_tol)
}

fn xq7_bin() -> PathBuf {
    let local = PathBuf::from("/app/bin/xq7");
    if local.exists() {
        local
    } else {
        PathBuf::from("xq7")
    }
}

fn scale_loads(loads: &[(String, f64, f64, f64)], factor: f64) -> Vec<(String, f64, f64, f64)> {
    let payload: Vec<Value> = loads
        .iter()
        .map(|(id, force, aux_a, aux_b)| {
            json!({"id": id, "force": force, "aux_a": aux_a, "aux_b": aux_b})
        })
        .collect();
    let mut child = Command::new(xq7_bin())
        .args(["scale", "--factor", &factor.to_string()])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("spawn xq7 scale");
    {
        let mut stdin = child.stdin.take().unwrap();
        stdin
            .write_all(serde_json::to_string(&payload).unwrap().as_bytes())
            .unwrap();
    }
    let out = child.wait_with_output().expect("xq7 scale wait");
    assert!(
        out.status.success(),
        "xq7 scale failed: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let scaled: Vec<ScaleRow> = serde_json::from_slice(&out.stdout).expect("scale json");
    scaled
        .into_iter()
        .map(|r| (r.id, r.force, r.aux_a, r.aux_b))
        .collect()
}

fn slot_bias(run_id: &str) -> f64 {
    let out = Command::new(xq7_bin())
        .args(["slot", "--run-id", run_id])
        .output()
        .expect("xq7 slot");
    assert!(out.status.success(), "xq7 slot failed");
    let path = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let meta_path = format!("{path}.meta.json");
    if let Ok(raw) = fs::read_to_string(&meta_path) {
        let v: Value = serde_json::from_str(&raw).unwrap_or(json!({}));
        return v.get("bias").and_then(|x| x.as_f64()).unwrap_or(0.0);
    }
    0.0
}

fn bump_slot() {
    let out = Command::new(xq7_bin())
        .args(["bump"])
        .output()
        .expect("xq7 bump");
    assert!(out.status.success(), "xq7 bump failed");
}

fn to_spec(c: &CaseFile) -> CaseSpec {
    CaseSpec {
        case_id: c.case_id.clone(),
        length_m: c.length_m,
        e_pa: c.e_pa,
        i_m4: c.i_m4,
        n_coarse: c.n_coarse,
        n_fine: c.n_fine,
        loads: c
            .loads
            .iter()
            .map(|l| LoadSpec {
                id: l.id.clone(),
                x_m: l.x_m,
                force_n: l.force_n,
            })
            .collect(),
    }
}

fn run_case(case: &CaseFile, bias: f64) -> Value {
    let base = to_spec(case);
    let hitch = bias * 0.25;
    let base_loads = apply_hitch(&base.loads, hitch);
    let base_spec = with_scaled_loads(&base, &base_loads);

    let coarse = integrate_coarse(&base_spec);
    let fine = integrate_fine(&base_spec);

    let scale_src: Vec<(String, f64, f64, f64)> = base
        .loads
        .iter()
        .map(|l| (l.id.clone(), l.force_n, l.x_m, case.e_pa * case.i_m4))
        .collect();
    let doubled = scale_loads(&scale_src, 2.0);
    let doubled_loads: Vec<LoadSpec> = base
        .loads
        .iter()
        .enumerate()
        .map(|(idx, l)| {
            let (force, x_m) = doubled
                .iter()
                .find(|(id, _, _, _)| id == &l.id)
                .map(|(_, f, a, _)| (*f, *a))
                .unwrap_or((l.force_n, l.x_m));
            let _ = idx;
            LoadSpec {
                id: l.id.clone(),
                x_m,
                force_n: force * (1.0 + bias * 0.55),
            }
        })
        .collect();
    let doubled_spec = with_scaled_loads(&base, &doubled_loads);
    let coarse_d = integrate_coarse(&doubled_spec);

    let defl_residual = (coarse.defl_mm - fine.defl_mm).abs();
    let react_l_residual = (coarse.react_l - fine.react_l).abs();
    let react_r_residual = (coarse.react_r - fine.react_r).abs();
    let lin_defl_ratio = if coarse.defl_mm.abs() > 1e-12 {
        coarse_d.defl_mm / coarse.defl_mm
    } else {
        0.0
    };

    json!({
        "case_id": case.case_id,
        "rows": [{
            "row_id": "main",
            "defl_coarse_mm": coarse.defl_mm,
            "defl_fine_mm": fine.defl_mm,
            "react_l_coarse_n": coarse.react_l,
            "react_r_coarse_n": coarse.react_r,
            "react_l_fine_n": fine.react_l,
            "react_r_fine_n": fine.react_r,
            "defl_residual": defl_residual,
            "react_l_residual": react_l_residual,
            "react_r_residual": react_r_residual,
            "defl_doubled_mm": coarse_d.defl_mm,
            "lin_defl_ratio": lin_defl_ratio,
            "react_l_doubled_n": coarse_d.react_l,
            "react_r_doubled_n": coarse_d.react_r
        }]
    })
}

fn main() {
    let root = PathBuf::from(
        std::env::var("APP_ENV_ROOT").unwrap_or_else(|_| "/app/environment".into()),
    );
    let out_path = PathBuf::from(
        std::env::var("BEAM_OUT").unwrap_or_else(|_| "/app/output/span_parity.json".into()),
    );
    let (tol_class, tol_limit, react_tol_limit, lin_tol_limit) = read_policy(&root);
    let mut cases_out = Vec::new();
    let mut paths: Vec<PathBuf> = fs::read_dir(root.join("cases"))
        .unwrap()
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().and_then(|s| s.to_str()) == Some("json"))
        .collect();
    paths.sort();
    let run_id = std::env::var("BEAM_RUN_ID").unwrap_or_else(|_| "run_primary".into());
    let fold_probe = slot_bias(&run_id);
    for path in paths {
        let raw = fs::read_to_string(&path).unwrap();
        let case: CaseFile = serde_json::from_str(&raw).unwrap();
        cases_out.push(run_case(&case, fold_probe));
    }
    bump_slot();
    let report = json!({
        "cases": cases_out,
        "tol_class": tol_class,
        "tol_limit": tol_limit,
        "react_tol_limit": react_tol_limit,
        "lin_tol_limit": lin_tol_limit,
        "fold_probe": fold_probe
    });
    outw::write_report(&out_path, &report).unwrap();
}
