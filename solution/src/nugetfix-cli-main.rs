use nugetfix_core::{audit, read_csv, report_to_json, Edge, PackageRow};
use std::collections::{HashMap, HashSet};
use std::env;
use std::process;

fn main() {
    let mut args: Vec<String> = env::args().skip(1).collect();
    if args.is_empty() { eprintln!("usage"); process::exit(2); }
    if args[0] == "--version" { println!("nugetfix 1.74.0"); return; }
    if args[0] != "audit" { eprintln!("unknown"); process::exit(2); }
    args.remove(0);
    let mut lane = String::new();
    let mut edges_p = String::new();
    let mut arts_p = String::new();
    let mut packages_p = String::new();
    let mut cache_p = String::new();
    let mut pins_p = String::new();
    let mut feedtags_p = String::new();
    let mut adv_p = String::new();
    let mut xor_p = String::new();
    let mut bans_p = String::new();
    let mut peers_p = String::new();
    let mut hops = 0u32;
    let mut out = String::new();
    let mut i = 0;
    while i < args.len() {
        let a = args[i].clone();
        let v = args.get(i + 1).cloned().unwrap_or_default();
        match a.as_str() {
            "--lane" => lane = v,
            "--edges" => edges_p = v,
            "--artifacts" => arts_p = v,
            "--packages" => packages_p = v,
            "--cache" => cache_p = v,
            "--pins" => pins_p = v,
            "--feedtags" => feedtags_p = v,
            "--advisories" => adv_p = v,
            "--xor" => xor_p = v,
            "--bans" => bans_p = v,
            "--peers" => peers_p = v,
            "--retention-hops" => hops = v.parse().unwrap_or(0),
            "--out" => out = v,
            _ => { eprintln!("unknown {a}"); process::exit(2); }
        }
        i += 2;
    }
    let edge_rows = filter_lane(&read_csv(&edges_p).expect("edges"), &lane);
    let edges: Vec<Edge> = edge_rows.iter().map(|r| Edge { parent: r[1].clone(), child: r[2].clone(), hard: r[3] == "hard" }).collect();
    let art_rows = filter_lane(&read_csv(&arts_p).expect("artifacts"), &lane);
    let artifacts: Vec<String> = art_rows.iter().map(|r| r[1].clone()).collect();
    let pkg_rows = filter_lane(&read_csv(&packages_p).expect("packages"), &lane);
    let packages: Vec<PackageRow> = pkg_rows.iter().map(|r| PackageRow {
        coordinate: r[1].clone(), name: r[2].clone(), version: r[3].clone(), wheel: r[4].clone(),
        platform_tag: r[5].clone(), digest: r[6].clone(), size_bytes: r[7].parse().unwrap_or(0),
    }).collect();
    let (_, cache_rows) = read_csv(&cache_p).expect("cache");
    let cache: HashSet<String> = cache_rows.into_iter().map(|r| r[0].clone()).collect();
    let (_, pin_rows) = read_csv(&pins_p).expect("pins");
    let pins: HashMap<String, String> = pin_rows.into_iter().map(|r| (r[0].clone(), r[1].clone())).collect();
    let (_, plat_rows) = read_csv(&feedtags_p).expect("feedtags");
    let feedtags: HashMap<String, String> = plat_rows.into_iter().map(|r| (r[0].clone(), r[1].clone())).collect();
    let (_, adv_rows) = read_csv(&adv_p).expect("advisories");
    let advisories: Vec<(String, String)> = adv_rows.into_iter().map(|r| (r[0].clone(), r[1].clone())).collect();
    let xor_rows_f = filter_lane(&read_csv(&xor_p).expect("xor"), &lane);
    let xor_rows: Vec<(String, String)> = xor_rows_f.iter().map(|r| (r[1].clone(), r[2].clone())).collect();
    let (_, ban_rows) = read_csv(&bans_p).expect("bans");
    let bans: HashSet<String> = ban_rows.into_iter().map(|r| r[0].clone()).collect();
    let peer_rows_f = filter_lane(&read_csv(&peers_p).expect("peers"), &lane);
    let peers: Vec<(String, String)> = peer_rows_f.iter().map(|r| (r[1].clone(), r[2].clone())).collect();
    let report = audit(&lane, hops, &edges, &artifacts, &packages, &cache, &pins, &feedtags, &advisories, &xor_rows, &bans, &peers);
    std::fs::write(&out, report_to_json(&report) + "\n").expect("write");
}

fn filter_lane(parsed: &(Vec<String>, Vec<Vec<String>>), lane: &str) -> Vec<Vec<String>> {
    parsed.1.iter().filter(|r| r.first().map(|c| c.as_str()) == Some(lane)).cloned().collect()
}
