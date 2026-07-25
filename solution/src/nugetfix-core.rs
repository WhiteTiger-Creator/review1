use nugetfix_graph::cascade_origins;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

pub use nugetfix_graph::Edge;

#[derive(Clone, Debug)]
pub struct PackageRow {
    pub coordinate: String,
    pub name: String,
    pub version: String,
    pub wheel: String,
    pub platform_tag: String,
    pub digest: String,
    pub size_bytes: u64,
}

#[derive(Clone, Debug)]
pub struct ArtifactReport {
    pub coordinate: String,
    pub status: String,
    pub holds: Vec<String>,
    pub risk_score: u32,
}

#[derive(Clone, Debug)]
pub struct AuditReport {
    pub lane: String,
    pub retention_hops: u32,
    pub artifacts: Vec<ArtifactReport>,
    pub totals: BTreeMap<String, u32>,
}

pub fn audit(
    lane: &str,
    retention_hops: u32,
    edges: &[Edge],
    artifacts: &[String],
    packages: &[PackageRow],
    cache: &HashSet<String>,
    pins: &HashMap<String, String>,
    feedtags: &HashMap<String, String>,
    advisories: &[(String, String)],
    xor_rows: &[(String, String)],
    bans: &HashSet<String>,
    peers: &[(String, String)],
) -> AuditReport {
    let art_set: HashSet<String> = artifacts.iter().cloned().collect();
    let mut risk: BTreeMap<String, BTreeMap<String, u32>> = BTreeMap::new();
    for a in artifacts {
        risk.insert(a.clone(), BTreeMap::new());
    }
    {
        let mut add = |coord: &str, hold: String, r: u32| {
            if let Some(m) = risk.get_mut(coord) {
                let e = m.entry(hold).or_insert(0);
                *e = (*e).max(r);
            }
        };
        for p in packages {
            if !art_set.contains(&p.coordinate) {
                continue;
            }
            if let Some(exp) = feedtags.get(&p.name) {
                if exp != &p.platform_tag {
                    add(&p.coordinate, format!("feedtag:{}:{}:{}", p.coordinate, exp, p.platform_tag), 42);
                }
            }
            if let Some(exp) = pins.get(&p.name) {
                if exp != &p.digest {
                    add(&p.coordinate, format!("hashdrift:{}:{}:{}", p.coordinate, exp, p.digest), 43);
                }
            }
            if !cache.contains(&p.digest) {
                add(&p.coordinate, format!("cachemiss:{}:{}", p.coordinate, p.digest), 40);
            }
        }
        let present: HashMap<String, String> = packages
            .iter()
            .filter(|p| art_set.contains(&p.coordinate))
            .map(|p| (p.name.clone(), p.coordinate.clone()))
            .collect();
        let present_names: HashSet<String> = present.keys().cloned().collect();
        let mut by_group: HashMap<String, BTreeSet<String>> = HashMap::new();
        for (group, name) in xor_rows {
            if present.contains_key(name) {
                by_group.entry(group.clone()).or_default().insert(name.clone());
            }
        }
        for (group, names) in by_group {
            if names.len() < 2 {
                continue;
            }
            let joined = names.iter().cloned().collect::<Vec<_>>().join("|");
            let hold = format!("xor:{}:{}", group, joined);
            for n in &names {
                if let Some(c) = present.get(n) {
                    add(c, hold.clone(), 52);
                }
            }
        }
        for (coord, peer_name) in peers {
            if art_set.contains(coord) && !present_names.contains(peer_name) {
                add(coord, format!("packagerefdrift:{}:{}", coord, peer_name), 41);
            }
        }
        for (coord, cve) in advisories {
            if art_set.contains(coord) {
                add(coord, format!("advisory:{}:{}", coord, cve), 49);
            }
        }
        for a in artifacts {
            if bans.contains(a) {
                add(a, format!("ban:{}", a), 55);
            }
        }
    }
    let mut origin_holds: HashMap<String, Vec<(String, u32)>> = HashMap::new();
    for (coord, map) in &risk {
        for (h, r) in map {
            if h.starts_with("ban:") || h.starts_with("xor:") || h.starts_with("packagerefdrift:") {
                origin_holds.entry(coord.clone()).or_default().push((h.clone(), *r));
            }
        }
    }
    let origins: HashSet<String> = origin_holds.keys().cloned().collect();
    let cascades = cascade_origins(edges, &origins, retention_hops);
    // Lex-smallest-origin collapse: same underlying hold keeps only the smallest origin.
    let mut best: HashMap<(String, String), (String, u32)> = HashMap::new();
    for (dep, ors) in cascades {
        for origin in ors {
            if let Some(hs) = origin_holds.get(&origin) {
                for (h, r) in hs {
                    let key = (dep.clone(), h.clone());
                    match best.get(&key) {
                        Some((prev, _)) if origin.as_str() >= prev.as_str() => {}
                        _ => {
                            best.insert(key, (origin.clone(), *r));
                        }
                    }
                }
            }
        }
    }
    for ((dep, h), (origin, r)) in best {
        if let Some(m) = risk.get_mut(&dep) {
            let e = m.entry(format!("cascade:{}:{}", origin, h)).or_insert(0);
            *e = (*e).max(r);
        }
    }
    let mut totals: BTreeMap<String, u32> = [
        "release", "hold", "feedtags", "hashdrifts", "cachemisses", "xors", "advisories", "bans", "packagerefdrifts", "cascades", "risk_score_total",
    ].into_iter().map(|k| (k.to_string(), 0u32)).collect();
    let mut reports = Vec::new();
    for coord in artifacts.iter().cloned().collect::<BTreeSet<_>>() {
        let map = risk.get(&coord).cloned().unwrap_or_default();
        let holds: Vec<String> = map.keys().cloned().collect();
        let score: u32 = map.values().sum();
        for h in &holds {
            if h.starts_with("feedtag:") { *totals.get_mut("feedtags").unwrap() += 1; }
            else if h.starts_with("hashdrift:") { *totals.get_mut("hashdrifts").unwrap() += 1; }
            else if h.starts_with("cachemiss:") { *totals.get_mut("cachemisses").unwrap() += 1; }
            else if h.starts_with("xor:") { *totals.get_mut("xors").unwrap() += 1; }
            else if h.starts_with("advisory:") { *totals.get_mut("advisories").unwrap() += 1; }
            else if h.starts_with("ban:") { *totals.get_mut("bans").unwrap() += 1; }
            else if h.starts_with("packagerefdrift:") { *totals.get_mut("packagerefdrifts").unwrap() += 1; }
            else if h.starts_with("cascade:") { *totals.get_mut("cascades").unwrap() += 1; }
        }
        let status = if holds.is_empty() {
            *totals.get_mut("release").unwrap() += 1;
            "release"
        } else {
            *totals.get_mut("hold").unwrap() += 1;
            "hold"
        };
        *totals.get_mut("risk_score_total").unwrap() += score;
        reports.push(ArtifactReport { coordinate: coord, status: status.into(), holds, risk_score: score });
    }
    AuditReport { lane: lane.into(), retention_hops, artifacts: reports, totals }
}

pub fn report_to_json(r: &AuditReport) -> String {
    let mut arts = String::from("[");
    for (i, a) in r.artifacts.iter().enumerate() {
        if i > 0 { arts.push(','); }
        let holds = a.holds.iter().map(|h| format!("\"{}\"", esc(h))).collect::<Vec<_>>().join(",");
        arts.push_str(&format!(
            "{{\"coordinate\":\"{}\",\"status\":\"{}\",\"holds\":[{}],\"risk_score\":{}}}",
            esc(&a.coordinate), esc(&a.status), holds, a.risk_score
        ));
    }
    arts.push(']');
    let mut totals = String::from("{");
    for (i, (k, v)) in r.totals.iter().enumerate() {
        if i > 0 { totals.push(','); }
        totals.push_str(&format!("\"{}\":{}", esc(k), v));
    }
    totals.push('}');
    format!("{{\"lane\":\"{}\",\"retention_hops\":{},\"artifacts\":{},\"totals\":{}}}", esc(&r.lane), r.retention_hops, arts, totals)
}

fn esc(s: &str) -> String { s.replace('\\', "\\\\").replace('"', "\\\"") }

pub fn read_csv(path: &str) -> Result<(Vec<String>, Vec<Vec<String>>), String> {
    let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut lines = text.lines().filter(|l| !l.trim().is_empty());
    let header = lines.next().ok_or_else(|| "missing header".to_string())?.split(',').map(|s| s.trim().to_string()).collect::<Vec<_>>();
    let rows = lines.map(|l| l.split(',').map(|s| s.trim().to_string()).collect()).collect();
    Ok((header, rows))
}
