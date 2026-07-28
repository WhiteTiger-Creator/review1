//! Bridge modal model schema decoding and canonical identity.

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::canonicalize::{json_string, render_f64, sha256_hex};
use crate::input::strict_json::{
    matrix_from_value, parse_object_with_code, reject_unknown, require_array, require_f64,
    require_string, validate_identifier,
};
use crate::linalg::dense::Matrix;
use serde_json::Value;
use std::collections::HashSet;
use std::path::Path;

#[derive(Clone, Debug)]
pub struct StiffnessGroup {
    pub group_id: String,
    pub lower: f64,
    pub upper: f64,
    pub initial: f64,
    pub reference: f64,
    pub contribution: Matrix,
}

#[derive(Clone, Debug)]
pub struct BridgeModel {
    pub dofs: Vec<String>,
    pub mass: Matrix,
    pub fixed_stiffness: Matrix,
    pub groups: Vec<StiffnessGroup>,
    pub model_sha256: String,
    pub raw_canonical: String,
}

pub fn load_model(path: &Path) -> AppResult<BridgeModel> {
    let bytes = crate::input::strict_json::read_bytes(path)?;
    decode_model(&bytes)
}

pub fn decode_model(bytes: &[u8]) -> AppResult<BridgeModel> {
    let code = FailureCode::EModelSchema;
    let map = parse_object_with_code(bytes, code)?;
    reject_unknown(
        &map,
        &["format", "dofs", "mass", "fixed_stiffness", "groups"],
        code,
    )?;
    let format = require_string(&map, "format", code)?;
    if format != "bridge-modal-model-v1" {
        return fail(code, "unsupported model format");
    }
    let dof_vals = require_array(&map, "dofs", code)?;
    if dof_vals.len() < 2 || dof_vals.len() > 24 {
        return fail(code, "dof count out of range");
    }
    let mut dofs = Vec::new();
    let mut seen = HashSet::new();
    for v in dof_vals {
        let id = match v {
            Value::String(s) => s.clone(),
            _ => return fail(code, "dof must be string"),
        };
        validate_identifier(&id, code)?;
        if !seen.insert(id.clone()) {
            return fail(code, format!("duplicate dof {id}"));
        }
        dofs.push(id);
    }
    let n = dofs.len();
    let mass_rows = matrix_from_value(map.get("mass").ok_or_else(|| (code, "missing mass".into()))?, n, code)?;
    let fixed_rows = matrix_from_value(
        map.get("fixed_stiffness")
            .ok_or_else(|| (code, "missing fixed_stiffness".into()))?,
        n,
        code,
    )?;
    let mut mass = Matrix::from_rows(&mass_rows).map_err(|e| (code, e))?;
    let mut fixed = Matrix::from_rows(&fixed_rows).map_err(|e| (code, e))?;
    mass.symmetrize_checked()
        .map_err(|e| (FailureCode::EMatrixSymmetry, e))?;
    fixed
        .symmetrize_checked()
        .map_err(|e| (FailureCode::EMatrixSymmetry, e))?;

    let group_vals = require_array(&map, "groups", code)?;
    if group_vals.is_empty() || group_vals.len() > 8 {
        return fail(code, "group count out of range");
    }
    let mut groups = Vec::new();
    let mut gseen = HashSet::new();
    for gv in group_vals {
        let gmap = match gv {
            Value::Object(m) => m,
            _ => return fail(code, "group must be object"),
        };
        reject_unknown(
            gmap,
            &[
                "group_id",
                "lower",
                "upper",
                "initial",
                "reference",
                "contribution",
            ],
            code,
        )?;
        let group_id = require_string(gmap, "group_id", code)?;
        validate_identifier(&group_id, code)?;
        if !gseen.insert(group_id.clone()) {
            return fail(code, format!("duplicate group {group_id}"));
        }
        let lower = require_f64(gmap, "lower", code)?;
        let upper = require_f64(gmap, "upper", code)?;
        let initial = require_f64(gmap, "initial", code)?;
        let reference = require_f64(gmap, "reference", code)?;
        if !(lower < upper) {
            return fail(code, "lower must be < upper");
        }
        if !(lower <= initial && initial <= upper) {
            return fail(code, "initial outside bounds");
        }
        if !(lower <= reference && reference <= upper) {
            return fail(code, "reference outside bounds");
        }
        let crow = matrix_from_value(
            gmap.get("contribution")
                .ok_or_else(|| (code, "missing contribution".into()))?,
            n,
            code,
        )?;
        let mut contribution = Matrix::from_rows(&crow).map_err(|e| (code, e))?;
        contribution
            .symmetrize_checked()
            .map_err(|e| (FailureCode::EMatrixSymmetry, e))?;
        groups.push(StiffnessGroup {
            group_id,
            lower,
            upper,
            initial,
            reference,
            contribution,
        });
    }

    let (canonical_dofs, order) = canonical_dof_order(&dofs);
    let mass_c = mass.permute(&order);
    let fixed_c = fixed.permute(&order);
    let mut groups_c: Vec<StiffnessGroup> = groups
        .iter()
        .map(|g| StiffnessGroup {
            group_id: g.group_id.clone(),
            lower: g.lower,
            upper: g.upper,
            initial: g.initial,
            reference: g.reference,
            contribution: g.contribution.permute(&order),
        })
        .collect();
    groups_c.sort_by(|a, b| a.group_id.cmp(&b.group_id));

    let raw_canonical = render_canonical_model(&canonical_dofs, &mass_c, &fixed_c, &groups_c);
    let model_sha256 = sha256_hex(raw_canonical.as_bytes());

    Ok(BridgeModel {
        dofs: canonical_dofs,
        mass: mass_c,
        fixed_stiffness: fixed_c,
        groups: groups_c,
        model_sha256,
        raw_canonical,
    })
}

pub fn canonical_dof_order(dofs: &[String]) -> (Vec<String>, Vec<usize>) {
    let mut indexed: Vec<(usize, &String)> = dofs.iter().enumerate().collect();
    indexed.sort_by(|a, b| a.1.cmp(b.1));
    let order: Vec<usize> = indexed.iter().map(|(i, _)| *i).collect();
    let names: Vec<String> = indexed.iter().map(|(_, s)| (*s).clone()).collect();
    (names, order)
}

fn render_matrix(m: &Matrix) -> String {
    let mut rows = Vec::new();
    for i in 0..m.n {
        let cols: Vec<String> = (0..m.n).map(|j| render_f64(m.get(i, j))).collect();
        rows.push(format!("    [{}]", cols.join(", ")));
    }
    format!("[\n{}\n  ]", rows.join(",\n"))
}

fn render_canonical_model(
    dofs: &[String],
    mass: &Matrix,
    fixed: &Matrix,
    groups: &[StiffnessGroup],
) -> String {
    let mut out = String::from("{\n");
    out.push_str("  \"format\": \"bridge-modal-model-v1\",\n");
    let dof_json: Vec<String> = dofs.iter().map(|d| json_string(d)).collect();
    out.push_str(&format!("  \"dofs\": [{}],\n", dof_json.join(", ")));
    out.push_str(&format!("  \"mass\": {},\n", render_matrix(mass)));
    out.push_str(&format!(
        "  \"fixed_stiffness\": {},\n",
        render_matrix(fixed)
    ));
    out.push_str("  \"groups\": [\n");
    for (gi, g) in groups.iter().enumerate() {
        out.push_str("    {\n");
        out.push_str(&format!(
            "      \"group_id\": {},\n",
            json_string(&g.group_id)
        ));
        out.push_str(&format!("      \"lower\": {},\n", render_f64(g.lower)));
        out.push_str(&format!("      \"upper\": {},\n", render_f64(g.upper)));
        out.push_str(&format!("      \"initial\": {},\n", render_f64(g.initial)));
        out.push_str(&format!(
            "      \"reference\": {},\n",
            render_f64(g.reference)
        ));
        // contribution matrix with deeper indent
        let mut crow = String::from("[\n");
        for i in 0..g.contribution.n {
            let cols: Vec<String> = (0..g.contribution.n)
                .map(|j| render_f64(g.contribution.get(i, j)))
                .collect();
            crow.push_str(&format!("        [{}]", cols.join(", ")));
            if i + 1 != g.contribution.n {
                crow.push(',');
            }
            crow.push('\n');
        }
        crow.push_str("      ]");
        out.push_str(&format!("      \"contribution\": {}\n", crow));
        out.push_str("    }");
        if gi + 1 != groups.len() {
            out.push(',');
        }
        out.push('\n');
    }
    out.push_str("  ]\n}\n");
    out
}
