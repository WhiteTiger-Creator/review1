use std::collections::BTreeMap;

pub type Pair = (String, String);

pub fn step_x(
    _tokens: &[String],
    _pairs: &[Pair],
    _dim: usize,
    _tau: f64,
    _lr: f64,
    _steps: usize,
) -> BTreeMap<String, Vec<f64>> {
    unimplemented!("pairwise-pull embedding update")
}
