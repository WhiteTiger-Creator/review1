use std::collections::BTreeMap;

pub fn step_y(
    hyp: &[String],
    gold: &[String],
    _emb: &BTreeMap<String, Vec<f64>>,
    _gamma: f64,
    _gap: f64,
) -> (f64, f64) {
    assert!(!hyp.is_empty() && !gold.is_empty());
    (0.0, 0.0)
}
