#!/bin/bash
set -euo pipefail

cat > /app/src/main.rs <<'RS'
use std::collections::HashMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::process::{Command, Stdio};

fn hex_to_bytes(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 || !s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) { return None; }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok()).collect()
}
fn bytes_to_hex(b: &[u8]) -> String { b.iter().map(|x| format!("{:02x}", x)).collect() }
fn sha256(data: &[u8]) -> Vec<u8> {
    let mut child = Command::new("sha256sum").stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap();
    child.stdin.as_mut().unwrap().write_all(data).unwrap();
    let out = child.wait_with_output().unwrap();
    hex_to_bytes(std::str::from_utf8(&out.stdout).unwrap().split_whitespace().next().unwrap()).unwrap()
}
fn leaf_hash(payload: &[u8]) -> Vec<u8> { let mut v = vec![0u8]; v.extend_from_slice(payload); sha256(&v) }
fn node_hash(left: &[u8], right: &[u8]) -> Vec<u8> { let mut v = vec![1u8]; v.extend_from_slice(left); v.extend_from_slice(right); sha256(&v) }
fn split_point(n: usize) -> usize { let mut k = 1usize; while (k << 1) < n { k <<= 1; } k }
fn tree_hash(leaves: &[Vec<u8>]) -> Vec<u8> { match leaves.len() { 0 => sha256(b""), 1 => leaf_hash(&leaves[0]), n => { let k = split_point(n); node_hash(&tree_hash(&leaves[..k]), &tree_hash(&leaves[k..])) } } }

fn expected_proof(old_size: usize, leaves: &[Vec<u8>]) -> Vec<Vec<u8>> {
    fn walk(old_n: usize, sub: &[Vec<u8>], out: &mut Vec<Vec<u8>>) {
        let new_n = sub.len();
        if old_n == 0 || old_n == new_n { return; }
        let k = split_point(new_n);
        if old_n <= k { out.push(tree_hash(&sub[k..])); walk(old_n, &sub[..k], out); }
        else { out.push(tree_hash(&sub[..k])); walk(old_n - k, &sub[k..], out); }
    }
    let mut out = Vec::new(); walk(old_size, leaves, &mut out); out
}

fn parse_case(path: &str) -> Result<HashMap<String, String>, &'static str> {
    let text = fs::read_to_string(path).map_err(|_| "MALFORMED")?;
    let mut m = HashMap::new();
    for line in text.lines() {
        let line = line.trim(); if line.is_empty() || line.starts_with('#') { continue; }
        let Some((k, v)) = line.split_once('=') else { return Err("MALFORMED"); };
        if k.is_empty() || m.contains_key(k) { return Err("MALFORMED"); }
        m.insert(k.to_string(), v.to_string());
    }
    Ok(m)
}
fn sig(public_key: &[u8], log_id: &[u8], size: usize, root_hex: &str) -> String {
    let mut v = Vec::new();
    v.extend_from_slice(public_key); v.extend_from_slice(b"CTSTH\0"); v.extend_from_slice(log_id); v.extend_from_slice(b"\0");
    v.extend_from_slice(size.to_string().as_bytes()); v.extend_from_slice(b"\0"); v.extend_from_slice(root_hex.as_bytes()); v.extend_from_slice(b"\0");
    bytes_to_hex(&sha256(&v))
}
fn parse_entries(v: &str) -> Result<Vec<Vec<u8>>, &'static str> {
    if v.is_empty() { return Ok(Vec::new()); }
    v.split(',').map(|x| hex_to_bytes(x).ok_or("MALFORMED")).collect()
}
fn parse_proof(v: &str) -> Result<Vec<Vec<u8>>, &'static str> {
    if v.is_empty() { return Ok(Vec::new()); }
    v.split(',').map(|x| {
        let b = hex_to_bytes(x).ok_or("MALFORMED")?;
        if b.len() != 32 { return Err("MALFORMED"); }
        Ok(b)
    }).collect()
}
fn run(path: &str) -> Result<(usize, String), &'static str> {
    let m = parse_case(path)?;
    for k in ["log_id","public_key","old_size","old_root","old_sig","new_size","new_root","new_sig","entries","proof"] { if !m.contains_key(k) { return Err("MALFORMED"); } }
    let log_id = hex_to_bytes(&m["log_id"]).ok_or("MALFORMED")?;
    let public_key = hex_to_bytes(&m["public_key"]).ok_or("MALFORMED")?;
    if log_id.len() != 9 || public_key.len() != 14 { return Err("MALFORMED"); }
    for k in ["old_root","old_sig","new_root","new_sig"] {
        if hex_to_bytes(&m[k]).ok_or("MALFORMED")?.len() != 32 { return Err("MALFORMED"); }
    }
    let old_size: usize = m["old_size"].parse().map_err(|_| "MALFORMED")?; let new_size: usize = m["new_size"].parse().map_err(|_| "MALFORMED")?;
    let entries = parse_entries(&m["entries"])?; let proof = parse_proof(&m["proof"])?;
    if entries.len() != new_size { return Err("MALFORMED"); }
    let state = fs::read_to_string("/app/state/trusted.sth").map_err(|_| "STATE")?;
    let parts: Vec<&str> = state.trim_end().split(' ').collect();
    if parts.len() != 3 || parts[0] != m["log_id"] || parts[1] != m["old_size"] || parts[2] != m["old_root"] { return Err("STATE"); }
    if sig(&public_key, &log_id, old_size, &m["old_root"]) != m["old_sig"] || sig(&public_key, &log_id, new_size, &m["new_root"]) != m["new_sig"] { return Err("SIGNATURE"); }
    if bytes_to_hex(&tree_hash(&entries)) != m["new_root"] { return Err("ROOT"); }
    if new_size < old_size { return Err("CONSISTENCY"); }
    if bytes_to_hex(&tree_hash(&entries[..old_size])) != m["old_root"] || proof != expected_proof(old_size, &entries) { return Err("CONSISTENCY"); }
    let tmp_path = "/app/state/trusted.sth.tmp";
    let next = format!("{} {} {}\n", m["log_id"], new_size, m["new_root"]);
    { let mut f = OpenOptions::new().create(true).truncate(true).write(true).open(tmp_path).map_err(|_| "STATE")?; f.write_all(next.as_bytes()).map_err(|_| "STATE")?; f.sync_all().map_err(|_| "STATE")?; }
    fs::rename(tmp_path, "/app/state/trusted.sth").map_err(|_| "STATE")?;
    OpenOptions::new().read(true).open("/app/state").and_then(|d| d.sync_all()).map_err(|_| "STATE")?;
    Ok((new_size, m["new_root"].clone()))
}
fn main() {
    let args: Vec<String> = env::args().collect(); if args.len() != 2 { std::process::exit(2); }
    match run(&args[1]) { Ok((n, r)) => println!("{{\"status\":\"ACCEPT\",\"tree_size\":{},\"root_hash\":\"{}\"}}", n, r), Err(e) => println!("{{\"status\":\"REJECT\",\"reason\":\"{}\"}}", e) }
}
RS

/usr/local/cargo/bin/cargo build --release --manifest-path /app/Cargo.toml
install -m 0755 /app/target/release/ctcheck /app/ctcheck
