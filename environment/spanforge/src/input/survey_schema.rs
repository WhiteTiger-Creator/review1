//! Ambient vibration survey schema and canonical identity.

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::input::canonicalize::{json_string, render_f64, sha256_hex};
use crate::input::strict_json::{
    parse_object_with_code, reject_unknown, require_array, require_f64, require_string,
    validate_identifier,
};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::path::Path;

#[derive(Clone, Debug)]
pub struct MeasuredMode {
    pub mode_id: String,
    pub frequency_hz: f64,
    pub weight: f64,
    pub shape: Vec<Option<f64>>,
}

#[derive(Clone, Debug)]
pub struct ModalSurvey {
    pub sensors: Vec<String>,
    pub modes: Vec<MeasuredMode>,
    pub survey_sha256: String,
}

pub fn load_survey(path: &Path, model_dofs: &[String]) -> AppResult<ModalSurvey> {
    let bytes = crate::input::strict_json::read_bytes(path)?;
    decode_survey(&bytes, model_dofs)
}

pub fn decode_survey(bytes: &[u8], model_dofs: &[String]) -> AppResult<ModalSurvey> {
    let code = FailureCode::ESurveySchema;
    let map = parse_object_with_code(bytes, code)?;
    reject_unknown(&map, &["format", "sensors", "modes"], code)?;
    let format = require_string(&map, "format", code)?;
    if format != "bridge-modal-survey-v1" {
        return fail(code, "unsupported survey format");
    }
    let sensor_vals = require_array(&map, "sensors", code)?;
    if sensor_vals.len() < 2 || sensor_vals.len() > 24 {
        return fail(code, "sensor count out of range");
    }
    let dof_set: HashSet<&str> = model_dofs.iter().map(|s| s.as_str()).collect();
    let mut sensors = Vec::new();
    let mut seen = HashSet::new();
    for v in sensor_vals {
        let id = match v {
            Value::String(s) => s.clone(),
            _ => return fail(code, "sensor must be string"),
        };
        validate_identifier(&id, code)?;
        if !dof_set.contains(id.as_str()) {
            return fail(code, format!("unknown sensor dof {id}"));
        }
        if !seen.insert(id.clone()) {
            return fail(code, format!("duplicate sensor {id}"));
        }
        sensors.push(id);
    }
    let mode_vals = require_array(&map, "modes", code)?;
    if mode_vals.len() < 2 || mode_vals.len() > 10 {
        return fail(code, "mode count out of range");
    }
    let mut modes = Vec::new();
    let mut mseen = HashSet::new();
    for mv in mode_vals {
        let mmap = match mv {
            Value::Object(m) => m,
            _ => return fail(code, "mode must be object"),
        };
        reject_unknown(mmap, &["mode_id", "frequency_hz", "weight", "shape"], code)?;
        let mode_id = require_string(mmap, "mode_id", code)?;
        validate_identifier(&mode_id, code)?;
        if !mseen.insert(mode_id.clone()) {
            return fail(code, format!("duplicate mode {mode_id}"));
        }
        let frequency_hz = require_f64(mmap, "frequency_hz", code)?;
        let weight = require_f64(mmap, "weight", code)?;
        if !(frequency_hz > 0.0 && weight > 0.0) {
            return fail(code, "frequency and weight must be positive");
        }
        let shape_vals = require_array(mmap, "shape", code)?;
        if shape_vals.len() != sensors.len() {
            return fail(code, "shape length must match sensors");
        }
        let mut shape = Vec::new();
        let mut finite = 0usize;
        for sv in shape_vals {
            match sv {
                Value::Null => shape.push(None),
                Value::Number(n) => {
                    let f = n.as_f64().ok_or_else(|| (code, "non-finite shape".into()))?;
                    if !f.is_finite() {
                        return fail(code, "non-finite shape entry");
                    }
                    shape.push(Some(f));
                    finite += 1;
                }
                _ => return fail(code, "shape entry must be number or null"),
            }
        }
        if finite < 2 {
            return fail(code, "mode has insufficient observed channels");
        }
        modes.push(MeasuredMode {
            mode_id,
            frequency_hz,
            weight,
            shape,
        });
    }

    // Canonical order: sensors sorted, shapes remapped; modes by freq then id
    let mut sensor_order: Vec<usize> = (0..sensors.len()).collect();
    sensor_order.sort_by(|&a, &b| sensors[a].cmp(&sensors[b]));
    let canon_sensors: Vec<String> = sensor_order.iter().map(|&i| sensors[i].clone()).collect();
    let mut canon_modes = modes.clone();
    for m in &mut canon_modes {
        let remapped: Vec<Option<f64>> = sensor_order.iter().map(|&i| m.shape[i]).collect();
        m.shape = remapped;
    }
    canon_modes.sort_by(|a, b| {
        a.frequency_hz
            .partial_cmp(&b.frequency_hz)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.mode_id.cmp(&b.mode_id))
    });
    let raw = render_canonical_survey(&canon_sensors, &canon_modes);
    let survey_sha256 = sha256_hex(raw.as_bytes());
    Ok(ModalSurvey {
        sensors: canon_sensors,
        modes: canon_modes,
        survey_sha256,
    })
}

fn render_canonical_survey(sensors: &[String], modes: &[MeasuredMode]) -> String {
    let mut out = String::from("{\n");
    out.push_str("  \"format\": \"bridge-modal-survey-v1\",\n");
    let sjson: Vec<String> = sensors.iter().map(|s| json_string(s)).collect();
    out.push_str(&format!("  \"sensors\": [{}],\n", sjson.join(", ")));
    out.push_str("  \"modes\": [\n");
    for (i, m) in modes.iter().enumerate() {
        out.push_str("    {\n");
        out.push_str(&format!("      \"mode_id\": {},\n", json_string(&m.mode_id)));
        out.push_str(&format!(
            "      \"frequency_hz\": {},\n",
            render_f64(m.frequency_hz)
        ));
        out.push_str(&format!("      \"weight\": {},\n", render_f64(m.weight)));
        let shape_parts: Vec<String> = m
            .shape
            .iter()
            .map(|o| match o {
                None => "null".into(),
                Some(v) => render_f64(*v),
            })
            .collect();
        out.push_str(&format!("      \"shape\": [{}]\n", shape_parts.join(", ")));
        out.push_str("    }");
        if i + 1 != modes.len() {
            out.push(',');
        }
        out.push('\n');
    }
    out.push_str("  ]\n}\n");
    out
}

pub fn sensor_index_map(sensors: &[String]) -> HashMap<String, usize> {
    sensors
        .iter()
        .enumerate()
        .map(|(i, s)| (s.clone(), i))
        .collect()
}
