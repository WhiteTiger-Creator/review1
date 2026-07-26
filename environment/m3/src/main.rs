mod warp;

use std::collections::BTreeMap;
use std::io::{BufRead, Write};

fn main() {
    let stdin = std::io::stdin();
    let mut gamma = 0.35;
    let mut gap = 0.45;
    let mut hyp = Vec::new();
    let mut gold = Vec::new();
    let mut emb: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    for line in stdin.lock().lines() {
        let line = line.unwrap();
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if line == "END" {
            break;
        }
        let mut parts = line.splitn(2, ' ');
        let cmd = parts.next().unwrap();
        let rest = parts.next().unwrap_or("");
        match cmd {
            "GAMMA" => gamma = rest.parse().unwrap(),
            "GAP" => gap = rest.parse().unwrap(),
            "HYP" => {
                hyp = rest
                    .split('|')
                    .map(|s| s.to_string())
                    .filter(|s| !s.is_empty())
                    .collect()
            }
            "REF" => {
                gold = rest
                    .split('|')
                    .map(|s| s.to_string())
                    .filter(|s| !s.is_empty())
                    .collect()
            }
            "E" => {
                let mut sp = rest.splitn(2, ' ');
                let tok = sp.next().unwrap().to_string();
                let nums = sp.next().unwrap();
                let v: Vec<f64> = nums.split(',').map(|x| x.parse().unwrap()).collect();
                emb.insert(tok, v);
            }
            _ => {}
        }
    }
    let (raw, score) = warp::step_y(&hyp, &gold, &emb, gamma, gap);
    writeln!(std::io::stdout(), "RAW {:.10}", raw).unwrap();
    writeln!(std::io::stdout(), "SCORE {:.10}", score).unwrap();
}
