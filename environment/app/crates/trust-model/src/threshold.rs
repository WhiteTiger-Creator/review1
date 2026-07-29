
use std::collections::{BTreeSet, HashMap};

pub fn count_distinct(values: &[String]) -> usize {
    values.iter().collect::<BTreeSet<_>>().len()
}

pub fn threshold_satisfied(
    approvals: &[(String, String)],
    minimum: usize,
) -> bool {

    let keys: Vec<String> = approvals
        .iter()
        .map(|(key, _)| key.clone())
        .collect();
    count_distinct(&keys) >= minimum
}

pub fn canonical_satisfying_set(
    approvals: &[(String, String)],
    minimum: usize,
) -> Vec<String> {

    let mut keys: Vec<String> = approvals
        .iter()
        .map(|(key, _)| key.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    keys.sort();
    keys.truncate(minimum);
    keys
}

pub fn principal_for_key<'a>(
    key_id: &str,
    mapping: &'a HashMap<String, String>,
) -> Option<&'a str> {
    mapping.get(key_id).map(String::as_str)
}
