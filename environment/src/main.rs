use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::Write;
use std::process::{Command, Stdio};

fn hex_to_bytes(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 || !s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
        return None;
    }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok()).collect()
}

fn bytes_to_hex(b: &[u8]) -> String {
    let mut out = String::new();
    for x in b { out.push_str(&format!("{:02x}", x)); }
    out
}

fn sha256(data: &[u8]) -> Vec<u8> {
    let mut child = Command::new("sha256sum").stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap();
    child.stdin.as_mut().unwrap().write_all(data).unwrap();
    let out = child.wait_with_output().unwrap();
    hex_to_bytes(std::str::from_utf8(&out.stdout).unwrap().split_whitespace().next().unwrap()).unwrap()
}

fn leaf_hash(payload: &[u8]) -> Vec<u8> { sha256(payload) }

fn node_hash(left: &[u8], right: &[u8]) -> Vec<u8> {
    let mut v = Vec::new(); v.extend_from_slice(left); v.extend_from_slice(right); sha256(&v)
}

fn split_point(n: usize) -> usize { let mut k = 1usize; while (k << 1) < n { k <<= 1; } k }

fn tree_hash(leaves: &[Vec<u8>]) -> Vec<u8> {
    match leaves.len() {
        0 => sha256(b""),
        1 => leaf_hash(&leaves[0]),
        n => { let k = split_point(n); node_hash(&tree_hash(&leaves[..k]), &tree_hash(&leaves[k..])) }
    }
}

fn parse_case(path: &str) -> Result<HashMap<String, String>, &'static str> {
    let text = fs::read_to_string(path).map_err(|_| "MALFORMED")?;
    let mut m = HashMap::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') { continue; }
        let Some((k, v)) = line.split_once('=') else { return Err("MALFORMED"); };
        if k.is_empty() || m.contains_key(k) { return Err("MALFORMED"); }
        m.insert(k.to_string(), v.to_string());
    }
    Ok(m)
}

fn sig(public_key: &[u8], log_id: &[u8], size: usize, root_hex: &str) -> String {
    let mut v = Vec::new();
    v.extend_from_slice(log_id); v.extend_from_slice(public_key); v.extend_from_slice(root_hex.as_bytes()); v.extend_from_slice(size.to_string().as_bytes());
    bytes_to_hex(&sha256(&v))
}

fn run(path: &str) -> Result<(usize, String), &'static str> {
    let m = parse_case(path)?;
    for k in ["log_id","public_key","old_size","old_root","old_sig","new_size","new_root","new_sig","entries","proof"] { if !m.contains_key(k) { return Err("MALFORMED"); } }
    let log_id = hex_to_bytes(&m["log_id"]).ok_or("MALFORMED")?;
    let public_key = hex_to_bytes(&m["public_key"]).ok_or("MALFORMED")?;
    let old_size: usize = m["old_size"].parse().map_err(|_| "MALFORMED")?;
    let new_size: usize = m["new_size"].parse().map_err(|_| "MALFORMED")?;
    hex_to_bytes(&m["old_root"]).ok_or("MALFORMED")?; hex_to_bytes(&m["new_root"]).ok_or("MALFORMED")?;
    let entries: Vec<Vec<u8>> = if m["entries"].is_empty() { vec![] } else { m["entries"].split(',').map(|x| hex_to_bytes(x).ok_or("MALFORMED")).collect::<Result<_,_>>()? };
    if entries.len() != new_size { return Err("MALFORMED"); }

    let state = fs::read_to_string("/app/state/trusted.sth").map_err(|_| "STATE")?;
    let parts: Vec<&str> = state.trim_end().split(' ').collect();
    if parts.len() != 3 || parts[0] != m["log_id"] || parts[1] != m["old_size"] || parts[2] != m["old_root"] { return Err("STATE"); }

    let tmp = format!("{} {} {}\n", m["log_id"], new_size, m["new_root"]);
    fs::write("/app/state/trusted.sth", &tmp).map_err(|_| "STATE")?;

    if sig(&public_key, &log_id, old_size, &m["old_root"]) != m["old_sig"] || sig(&public_key, &log_id, new_size, &m["new_root"]) != m["new_sig"] { return Err("SIGNATURE"); }
    if new_size < old_size { return Err("CONSISTENCY"); }
    if bytes_to_hex(&tree_hash(&entries)) != m["new_root"] { return Err("ROOT"); }
    Ok((new_size, m["new_root"].clone()))
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 { std::process::exit(2); }
    match run(&args[1]) {
        Ok((n, r)) => println!("{{\"status\":\"ACCEPT\",\"tree_size\":{},\"root_hash\":\"{}\"}}", n, r),
        Err(e) => println!("{{\"status\":\"REJECT\",\"reason\":\"{}\"}}", e),
    }
}
