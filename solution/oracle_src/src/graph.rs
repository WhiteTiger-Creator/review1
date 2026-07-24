use std::collections::{HashMap, HashSet};

use crate::checksum::{cmp_utf8, smallest_scc};
use crate::model::{Runbook, Step};

pub fn transitive_closure(
    seeds: &HashSet<String>,
    runbooks: &HashMap<String, Runbook>,
) -> (HashSet<String>, Option<&'static str>, Vec<String>) {
    // Missing seeds themselves are reported as missing_dependency using UTF-8 order.
    let mut missing_seeds: Vec<String> = seeds
        .iter()
        .filter(|id| !runbooks.contains_key(id.as_str()))
        .cloned()
        .collect();
    missing_seeds.sort_by(|a, b| cmp_utf8(a, b));
    if let Some(missing) = missing_seeds.into_iter().next() {
        return (HashSet::new(), Some("missing_dependency"), vec![missing]);
    }

    // Discover every reachable known runbook from the known seeds.
    // Expansion order is canonical so the selected set never depends on HashSet
    // iteration, requires-array order, or YAML file order.
    let mut selected: HashSet<String> = HashSet::new();
    let mut frontier: Vec<String> = seeds.iter().cloned().collect();
    frontier.sort_by(|a, b| cmp_utf8(a, b));
    while !frontier.is_empty() {
        let mut next: Vec<String> = Vec::new();
        for rid in &frontier {
            if selected.contains(rid) {
                continue;
            }
            selected.insert(rid.clone());
            if let Some(rb) = runbooks.get(rid) {
                for dep in &rb.requires {
                    if runbooks.contains_key(dep) && !selected.contains(dep) {
                        next.push(dep.clone());
                    }
                }
            }
        }
        next.sort_by(|a, b| cmp_utf8(a, b));
        next.dedup();
        frontier = next
            .into_iter()
            .filter(|id| !selected.contains(id))
            .collect();
    }

    // Record every missing edge independently of requires-array order, then
    // select by (requesting_runbook_id, missing_dependency_id) UTF-8 order.
    let mut missing_edges: Vec<(String, String)> = Vec::new();
    for rid in &selected {
        if let Some(rb) = runbooks.get(rid) {
            for dep in &rb.requires {
                if !runbooks.contains_key(dep) {
                    missing_edges.push((rid.clone(), dep.clone()));
                }
            }
        }
    }
    missing_edges.sort_by(|a, b| {
        (a.0.as_bytes(), a.1.as_bytes()).cmp(&(b.0.as_bytes(), b.1.as_bytes()))
    });
    if let Some((_requester, missing)) = missing_edges.into_iter().next() {
        return (HashSet::new(), Some("missing_dependency"), vec![missing]);
    }

    (selected, None, Vec::new())
}

pub fn find_runbook_cycle(
    selected: &HashSet<String>,
    runbooks: &HashMap<String, Runbook>,
) -> Option<Vec<String>> {
    let mut graph: HashMap<String, Vec<String>> = HashMap::new();
    for rid in selected {
        if let Some(rb) = runbooks.get(rid) {
            for dep in &rb.requires {
                if selected.contains(dep) {
                    graph.entry(rid.clone()).or_default().push(dep.clone());
                }
            }
        }
    }
    let mut index = 0usize;
    let mut indices: HashMap<String, usize> = HashMap::new();
    let mut lowlink: HashMap<String, usize> = HashMap::new();
    let mut stack: Vec<String> = Vec::new();
    let mut onstack: HashSet<String> = HashSet::new();
    let mut components: Vec<Vec<String>> = Vec::new();

    fn strongconnect(
        v: &str,
        graph: &HashMap<String, Vec<String>>,
        index: &mut usize,
        indices: &mut HashMap<String, usize>,
        lowlink: &mut HashMap<String, usize>,
        stack: &mut Vec<String>,
        onstack: &mut HashSet<String>,
        components: &mut Vec<Vec<String>>,
    ) {
        indices.insert(v.to_string(), *index);
        lowlink.insert(v.to_string(), *index);
        *index += 1;
        stack.push(v.to_string());
        onstack.insert(v.to_string());
        for w in graph.get(v).cloned().unwrap_or_default() {
            if !indices.contains_key(&w) {
                strongconnect(
                    &w, graph, index, indices, lowlink, stack, onstack, components,
                );
                let lv = *lowlink.get(v).unwrap();
                let lw = *lowlink.get(&w).unwrap();
                lowlink.insert(v.to_string(), lv.min(lw));
            } else if onstack.contains(&w) {
                let lv = *lowlink.get(v).unwrap();
                let iw = *indices.get(&w).unwrap();
                lowlink.insert(v.to_string(), lv.min(iw));
            }
        }
        if lowlink.get(v) == indices.get(v) {
            let mut comp = Vec::new();
            loop {
                let w = stack.pop().unwrap();
                onstack.remove(&w);
                comp.push(w.clone());
                if w == v {
                    break;
                }
            }
            if comp.len() > 1 {
                components.push(comp);
            }
        }
    }

    let mut nodes: Vec<String> = selected.iter().cloned().collect();
    nodes.sort_by(|a, b| cmp_utf8(a, b));
    for node in nodes {
        if !indices.contains_key(&node) {
            strongconnect(
                &node,
                &graph,
                &mut index,
                &mut indices,
                &mut lowlink,
                &mut stack,
                &mut onstack,
                &mut components,
            );
        }
    }
    if components.is_empty() {
        None
    } else {
        Some(smallest_scc(&components))
    }
}

pub fn topo_runbooks(
    effective: &HashSet<String>,
    runbooks: &HashMap<String, Runbook>,
    replacement_map: &HashMap<String, String>,
) -> Vec<String> {
    let mut edges: Vec<(String, String)> = Vec::new();
    for rid in effective {
        if let Some(rb) = runbooks.get(rid) {
            for raw_dep in &rb.requires {
                let satisfied = replacement_map
                    .get(raw_dep)
                    .cloned()
                    .unwrap_or_else(|| raw_dep.clone());
                if effective.contains(&satisfied) {
                    edges.push((satisfied, rid.clone()));
                }
            }
        }
    }
    let mut indegree: HashMap<String, usize> = effective.iter().map(|n| (n.clone(), 0)).collect();
    let mut adj: HashMap<String, Vec<String>> =
        effective.iter().map(|n| (n.clone(), Vec::new())).collect();
    for (src, dst) in edges {
        adj.get_mut(&src).unwrap().push(dst.clone());
        *indegree.get_mut(&dst).unwrap() += 1;
    }
    let mut ready: Vec<String> = indegree
        .iter()
        .filter(|(_, deg)| **deg == 0)
        .map(|(n, _)| n.clone())
        .collect();
    ready.sort_by(|a, b| {
        let ra = &runbooks[a];
        let rb = &runbooks[b];
        (ra.plan_rank, a.as_bytes()).cmp(&(rb.plan_rank, b.as_bytes()))
    });
    let mut order = Vec::new();
    while !ready.is_empty() {
        ready.sort_by(|a, b| {
            let ra = &runbooks[a];
            let rb = &runbooks[b];
            (ra.plan_rank, a.as_bytes()).cmp(&(rb.plan_rank, b.as_bytes()))
        });
        let node = ready.remove(0);
        order.push(node.clone());
        let mut nexts = adj.get(&node).cloned().unwrap_or_default();
        nexts.sort_by(|a, b| cmp_utf8(a, b));
        for nxt in nexts {
            let entry = indegree.get_mut(&nxt).unwrap();
            *entry -= 1;
            if *entry == 0 {
                ready.push(nxt);
            }
        }
    }
    order
}

pub fn find_step_cycle(steps: &[Step]) -> Option<Vec<String>> {
    let ids: HashSet<String> = steps.iter().map(|s| s.step_id.clone()).collect();
    let mut graph: HashMap<String, Vec<String>> = HashMap::new();
    for s in steps {
        for dep in &s.requires_step_ids {
            if !ids.contains(dep) {
                return None;
            }
            graph
                .entry(s.step_id.clone())
                .or_default()
                .push(dep.clone());
        }
    }
    let mut index = 0usize;
    let mut indices: HashMap<String, usize> = HashMap::new();
    let mut lowlink: HashMap<String, usize> = HashMap::new();
    let mut stack: Vec<String> = Vec::new();
    let mut onstack: HashSet<String> = HashSet::new();
    let mut components: Vec<Vec<String>> = Vec::new();

    fn strongconnect(
        v: &str,
        graph: &HashMap<String, Vec<String>>,
        index: &mut usize,
        indices: &mut HashMap<String, usize>,
        lowlink: &mut HashMap<String, usize>,
        stack: &mut Vec<String>,
        onstack: &mut HashSet<String>,
        components: &mut Vec<Vec<String>>,
    ) {
        indices.insert(v.to_string(), *index);
        lowlink.insert(v.to_string(), *index);
        *index += 1;
        stack.push(v.to_string());
        onstack.insert(v.to_string());
        for w in graph.get(v).cloned().unwrap_or_default() {
            if !indices.contains_key(&w) {
                strongconnect(
                    &w, graph, index, indices, lowlink, stack, onstack, components,
                );
                let lv = *lowlink.get(v).unwrap();
                let lw = *lowlink.get(&w).unwrap();
                lowlink.insert(v.to_string(), lv.min(lw));
            } else if onstack.contains(&w) {
                let lv = *lowlink.get(v).unwrap();
                let iw = *indices.get(&w).unwrap();
                lowlink.insert(v.to_string(), lv.min(iw));
            }
        }
        if lowlink.get(v) == indices.get(v) {
            let mut comp = Vec::new();
            loop {
                let w = stack.pop().unwrap();
                onstack.remove(&w);
                comp.push(w.clone());
                if w == v {
                    break;
                }
            }
            if comp.len() > 1 {
                components.push(comp);
            }
        }
    }

    let mut nodes: Vec<String> = ids.into_iter().collect();
    nodes.sort_by(|a, b| cmp_utf8(a, b));
    for node in nodes {
        if !indices.contains_key(&node) {
            strongconnect(
                &node,
                &graph,
                &mut index,
                &mut indices,
                &mut lowlink,
                &mut stack,
                &mut onstack,
                &mut components,
            );
        }
    }
    if components.is_empty() {
        None
    } else {
        Some(smallest_scc(&components))
    }
}

pub fn topo_steps(steps: &[Step]) -> Vec<Step> {
    let by_id: HashMap<String, &Step> = steps.iter().map(|s| (s.step_id.clone(), s)).collect();
    let mut indegree: HashMap<String, usize> =
        steps.iter().map(|s| (s.step_id.clone(), 0)).collect();
    let mut adj: HashMap<String, Vec<String>> = steps
        .iter()
        .map(|s| (s.step_id.clone(), Vec::new()))
        .collect();
    for s in steps {
        for dep in &s.requires_step_ids {
            adj.get_mut(dep).unwrap().push(s.step_id.clone());
            *indegree.get_mut(&s.step_id).unwrap() += 1;
        }
    }
    let mut ready: Vec<String> = indegree
        .iter()
        .filter(|(_, deg)| **deg == 0)
        .map(|(sid, _)| sid.clone())
        .collect();
    let mut order = Vec::new();
    while !ready.is_empty() {
        ready.sort_by(|a, b| {
            let sa = by_id[a];
            let sb = by_id[b];
            (sa.step_rank, a.as_bytes()).cmp(&(sb.step_rank, b.as_bytes()))
        });
        let node = ready.remove(0);
        order.push(node.clone());
        let mut nexts = adj.get(&node).cloned().unwrap_or_default();
        nexts.sort_by(|a, b| cmp_utf8(a, b));
        for nxt in nexts {
            let entry = indegree.get_mut(&nxt).unwrap();
            *entry -= 1;
            if *entry == 0 {
                ready.push(nxt);
            }
        }
    }
    order.into_iter().map(|sid| by_id[&sid].clone()).collect()
}
