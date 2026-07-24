use std::collections::{HashMap, HashSet};

use crate::checksum::cmp_utf8;
use crate::compatibility::has_checksum_drift;
use crate::graph::transitive_closure;
use crate::model::{Deployment, ReleaseProfile, Runbook};

fn replacement_failure_rank(reason: &str) -> Option<i32> {
    match reason {
        "missing_dependency" => Some(3),
        "applied_checksum_drift" => Some(5),
        "replacement_unsatisfied" => Some(6),
        _ => None,
    }
}

fn classify_replacement_pair(
    old_id: &str,
    new_id: &str,
    dep: &Deployment,
    runbooks: &HashMap<String, Runbook>,
    target_api: &str,
    target_db: &str,
) -> Option<(&'static str, Vec<String>)> {
    if !runbooks.contains_key(new_id) {
        return Some((
            "replacement_unsatisfied",
            vec![old_id.to_string(), new_id.to_string()],
        ));
    }
    let new_rb = &runbooks[new_id];
    if !new_rb.replaces.iter().any(|x| x == old_id)
        || !new_rb.provides_runbook_ids.iter().any(|x| x == old_id)
    {
        return Some((
            "replacement_unsatisfied",
            vec![old_id.to_string(), new_id.to_string()],
        ));
    }
    if !new_rb
        .allowed_api_revisions
        .contains(&target_api.to_string())
    {
        return Some((
            "replacement_unsatisfied",
            vec![old_id.to_string(), new_id.to_string()],
        ));
    }
    if !new_rb
        .allowed_database_revisions
        .contains(&target_db.to_string())
    {
        return Some((
            "replacement_unsatisfied",
            vec![old_id.to_string(), new_id.to_string()],
        ));
    }
    let old_rb = &runbooks[old_id];
    if has_checksum_drift(dep, old_rb) {
        return Some(("applied_checksum_drift", vec![old_id.to_string()]));
    }
    if has_checksum_drift(dep, new_rb) {
        return Some(("applied_checksum_drift", vec![new_id.to_string()]));
    }
    for dep_id in &new_rb.requires {
        if !runbooks.contains_key(dep_id) {
            return Some((
                "replacement_unsatisfied",
                vec![new_id.to_string(), dep_id.clone()],
            ));
        }
    }
    let seed: HashSet<String> = new_rb.requires.iter().cloned().collect();
    let (_extra, err, rel) = transitive_closure(&seed, runbooks);
    if let Some(err) = err {
        return Some((err, rel));
    }
    None
}

pub fn resolve_replacements(
    selected: &HashSet<String>,
    direct_targets: &HashSet<String>,
    dep: &Deployment,
    runbooks: &HashMap<String, Runbook>,
    profile: &ReleaseProfile,
    target_api: &str,
    target_db: &str,
) -> (
    HashSet<String>,
    HashMap<String, String>,
    Option<&'static str>,
    Vec<String>,
) {
    let mut pairs: Vec<(String, String)> = profile
        .replacement_preferences
        .iter()
        .map(|(old_id, new_id)| (old_id.clone(), new_id.clone()))
        .collect();
    pairs.sort_by(|a, b| {
        (a.0.as_bytes(), a.1.as_bytes()).cmp(&(b.0.as_bytes(), b.1.as_bytes()))
    });

    let mut applicable: Vec<(String, String)> = Vec::new();
    for (old_id, new_id) in &pairs {
        if selected.contains(old_id) && !direct_targets.contains(old_id) {
            applicable.push((old_id.clone(), new_id.clone()));
        }
    }

    // Collect failures across all applicable pairs, then select by published
    // cross-reason precedence (not by first canonical unsatisfied pair).
    let mut best: Option<(i32, &'static str, Vec<String>)> = None;
    for (old_id, new_id) in &applicable {
        if let Some((reason, rel)) =
            classify_replacement_pair(old_id, new_id, dep, runbooks, target_api, target_db)
        {
            let rank = replacement_failure_rank(reason).unwrap_or(100);
            match &best {
                None => best = Some((rank, reason, rel)),
                Some((best_rank, _, _)) if rank < *best_rank => {
                    best = Some((rank, reason, rel));
                }
                Some((best_rank, _, _)) if rank == *best_rank => {
                    // Same reason: keep the earlier canonical pair (already sorted).
                }
                _ => {}
            }
        }
    }
    if let Some((_, reason, rel)) = best {
        return (HashSet::new(), HashMap::new(), Some(reason), rel);
    }

    let mut effective = selected.clone();
    let mut replacement_map: HashMap<String, String> = HashMap::new();
    for (old_id, new_id) in &applicable {
        let new_rb = &runbooks[new_id];
        effective.insert(new_id.clone());
        effective.remove(old_id);
        replacement_map.insert(old_id.clone(), new_id.clone());
        let seed: HashSet<String> = new_rb.requires.iter().cloned().collect();
        let (extra, err, rel) = transitive_closure(&seed, runbooks);
        if let Some(err) = err {
            // Classification already passed; this is a defensive path only.
            return (HashSet::new(), HashMap::new(), Some(err), rel);
        }
        effective.extend(extra);
    }
    (effective, replacement_map, None, Vec::new())
}

pub fn detect_conflicts(
    effective: &HashSet<String>,
    runbooks: &HashMap<String, Runbook>,
) -> Option<&'static str> {
    let mut members: Vec<String> = effective.iter().cloned().collect();
    members.sort_by(|a, b| cmp_utf8(a, b));
    for a in &members {
        if let Some(rb) = runbooks.get(a) {
            for b in &rb.conflicts {
                if effective.contains(b) {
                    return Some("selected_runbook_conflict");
                }
            }
        }
    }
    None
}

pub fn selection_reason(
    rid: &str,
    direct_targets: &HashSet<String>,
    replacement_map: &HashMap<String, String>,
) -> String {
    if direct_targets.contains(rid) {
        return "requested".to_string();
    }
    if replacement_map.values().any(|v| v == rid) {
        return "replacement".to_string();
    }
    "dependency".to_string()
}
