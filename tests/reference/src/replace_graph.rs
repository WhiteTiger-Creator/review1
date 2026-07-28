use crate::error::{AuditorError, RequestFailure};
use crate::coalesce::{ConfigValue, MergedConfig};
use crate::report::{PathResolutionRow, ReplacementEdgeRow, SourceRow};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

#[derive(Debug, Clone)]
pub struct TerminalSource {
    pub name: String,
    pub kind: String, // directory | local-registry
    pub root_rel: String,
}

pub fn analyze(
    request_id: &str,
    _fixture_root: &Path,
    merged: &MergedConfig,
    path_rows: &[PathResolutionRow],
) -> Result<
    (
        Vec<SourceRow>,
        Vec<ReplacementEdgeRow>,
        BTreeMap<String, TerminalSource>,
    ),
    AuditorError,
> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for key in merged.values.keys() {
        if let Some(rest) = key.strip_prefix("source.") {
            if let Some((name, _)) = rest.split_once('.') {
                names.insert(name.to_string());
            }
        }
    }

    let path_index: BTreeMap<String, String> = path_rows
        .iter()
        .map(|r| (r.key.clone(), r.normalized_path.clone()))
        .collect();

    let mut replace_with: BTreeMap<String, String> = BTreeMap::new();
    let mut directory: BTreeMap<String, String> = BTreeMap::new();
    let mut local_registry: BTreeMap<String, String> = BTreeMap::new();

    for name in &names {
        let rw = key_string(merged, &format!("source.{name}.replace-with"));
        let dir = path_index
            .get(&format!("source.{name}.directory"))
            .cloned()
            .or_else(|| key_string(merged, &format!("source.{name}.directory")));
        let lr = path_index
            .get(&format!("source.{name}.local-registry"))
            .cloned()
            .or_else(|| key_string(merged, &format!("source.{name}.local-registry")));
        if let Some(v) = rw {
            replace_with.insert(name.clone(), v);
        }
        if let Some(v) = dir {
            directory.insert(name.clone(), v);
        }
        if let Some(v) = lr {
            local_registry.insert(name.clone(), v);
        }
    }

    // Follow chains; detect cycles
    let mut terminal_of: BTreeMap<String, String> = BTreeMap::new();
    let mut edges = Vec::new();
    for name in &names {
        let mut seen = Vec::new();
        let mut cur = name.clone();
        let mut edge_index = 0u32;
        loop {
            if seen.contains(&cur) {
                return Err(AuditorError::Request(RequestFailure {
                    request_id: request_id.into(),
                    stage: "source".into(),
                    reason: "replacement_cycle".into(),
                    path_or_source: Some(cur),
                    details: format!("replacement cycle involving {name}"),
                }));
            }
            seen.push(cur.clone());
            if let Some(next) = replace_with.get(&cur).cloned() {
                let known = names.contains(&next)
                    || replace_with.contains_key(&next)
                    || directory.contains_key(&next)
                    || local_registry.contains_key(&next);
                if !known {
                    return Err(AuditorError::Request(RequestFailure {
                        request_id: request_id.into(),
                        stage: "source".into(),
                        reason: "missing_replacement_target".into(),
                        path_or_source: Some(next.clone()),
                        details: format!("{cur} replace-with missing target"),
                    }));
                }
                edge_index += 1;
                edges.push(ReplacementEdgeRow {
                    request_id: request_id.to_string(),
                    from_source: cur.clone(),
                    to_source: next.clone(),
                    edge_index,
                });
                cur = next;
                continue;
            }
            // terminal
            let has_dir = directory.contains_key(&cur);
            let has_lr = local_registry.contains_key(&cur);
            if has_dir == has_lr {
                return Err(AuditorError::Request(RequestFailure {
                    request_id: request_id.into(),
                    stage: "source".into(),
                    reason: "ambiguous_terminal_source".into(),
                    path_or_source: Some(cur),
                    details: "terminal source must define exactly one of directory or local-registry"
                        .into(),
                }));
            }
            terminal_of.insert(name.clone(), cur);
            break;
        }
    }

    let mut source_rows = Vec::new();
    let mut terminals = BTreeMap::new();
    let mut all_names: BTreeSet<String> = names.iter().cloned().collect();
    for n in replace_with.keys() {
        all_names.insert(n.clone());
    }
    for n in directory.keys() {
        all_names.insert(n.clone());
    }
    for n in local_registry.keys() {
        all_names.insert(n.clone());
    }

    for name in &all_names {
        let term = terminal_of
            .get(name)
            .cloned()
            .unwrap_or_else(|| name.clone());
        let (kind, root) = if let Some(p) = directory.get(name) {
            ("directory".to_string(), Some(p.clone()))
        } else if let Some(p) = local_registry.get(name) {
            ("local-registry".to_string(), Some(p.clone()))
        } else if replace_with.contains_key(name) {
            ("replace".to_string(), None)
        } else {
            ("replace".to_string(), None)
        };
        if root.is_some() && !replace_with.contains_key(name) {
            terminals.insert(
                name.clone(),
                TerminalSource {
                    name: name.clone(),
                    kind: kind.clone(),
                    root_rel: root.clone().unwrap(),
                },
            );
        }
        // Also record terminal for chain ends
        if let Some(tname) = terminal_of.get(name) {
            if let Some(p) = directory.get(tname) {
                terminals.insert(
                    tname.clone(),
                    TerminalSource {
                        name: tname.clone(),
                        kind: "directory".into(),
                        root_rel: p.clone(),
                    },
                );
            } else if let Some(p) = local_registry.get(tname) {
                terminals.insert(
                    tname.clone(),
                    TerminalSource {
                        name: tname.clone(),
                        kind: "local-registry".into(),
                        root_rel: p.clone(),
                    },
                );
            }
        }
        source_rows.push(SourceRow {
            request_id: request_id.to_string(),
            source_name: name.clone(),
            source_kind: kind,
            replace_with_or_null: replace_with.get(name).cloned(),
            terminal_source: term,
            root_path_or_null: root,
        });
    }
    source_rows.sort_by(|a, b| a.source_name.cmp(&b.source_name));
    edges.sort_by(|a, b| {
        (&a.from_source, a.edge_index, &a.to_source).cmp(&(
            &b.from_source,
            b.edge_index,
            &b.to_source,
        ))
    });
    Ok((source_rows, edges, terminals))
}

fn key_string(merged: &MergedConfig, key: &str) -> Option<String> {
    match merged.values.get(key).map(|c| &c.value) {
        Some(ConfigValue::String(s)) => Some(s.clone()),
        _ => None,
    }
}
