mod kn;

use std::collections::BTreeMap;
use std::io::{BufRead, Write};

fn main() {
    let stdin = std::io::stdin();
    let mut dim = 4usize;
    let mut tau = 0.5;
    let mut lr = 0.25;
    let mut steps = 1usize;
    let mut tokens = Vec::new();
    let mut pairs = Vec::new();
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
            "DIM" => dim = rest.parse().unwrap(),
            "TAU" => tau = rest.parse().unwrap(),
            "LR" => lr = rest.parse().unwrap(),
            "STEPS" => steps = rest.parse().unwrap(),
            "TOKEN" => tokens.push(rest.to_string()),
            "PAIR" => {
                let mut ap = rest.splitn(2, '|');
                let a = ap.next().unwrap().to_string();
                let p = ap.next().unwrap().to_string();
                pairs.push((a, p));
            }
            _ => {}
        }
    }
    let emb = kn::step_x(&tokens, &pairs, dim, tau, lr, steps);
    write_out(&emb);
}

fn write_out(emb: &BTreeMap<String, Vec<f64>>) {
    let mut out = String::new();
    out.push_str("BEGIN\n");
    for (k, v) in emb {
        let nums: Vec<String> = v.iter().map(|x| format!("{:.10}", x)).collect();
        out.push_str(&format!("E {} {}\n", k, nums.join(",")));
    }
    out.push_str("END\n");
    std::io::stdout().write_all(out.as_bytes()).unwrap();
}
