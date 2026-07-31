//! kxtool - offline workbench for KXF1 firmware images.

mod cpu;
mod decode;
mod image;
mod recover;

use cpu::Machine;
use std::process::exit;

fn fail(code: &str, detail: &str) -> ! {
    eprintln!("{{\"error\":\"{}\",\"detail\":\"{}\"}}", code, escape(detail));
    exit(2);
}

fn escape(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

struct Args {
    cmd: String,
    image: Option<String>,
    key: Vec<u8>,
    addr: u16,
    count: usize,
    live: bool,
}

fn parse_args() -> Args {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.is_empty() {
        fail("bad_argument", "usage: kxtool <disasm|run|map|recover> --image PATH [...]");
    }
    let mut a = Args {
        cmd: argv[0].clone(),
        image: None,
        key: Vec::new(),
        addr: 0,
        count: 16,
        live: false,
    };
    if !matches!(a.cmd.as_str(), "disasm" | "run" | "map" | "recover") {
        fail("bad_argument", &format!("unknown subcommand {}", a.cmd));
    }
    let mut i = 1;
    let mut saw_addr = false;
    while i < argv.len() {
        let k = argv[i].clone();
        if k == "--live" {
            a.live = true;
            i += 1;
            continue;
        }
        if i + 1 >= argv.len() {
            fail("bad_argument", &format!("option {} is missing its value", k));
        }
        let v = argv[i + 1].clone();
        match k.as_str() {
            "--image" => a.image = Some(v),
            "--key" => a.key = parse_hex(&v),
            "--addr" => {
                a.addr = parse_u16(&v);
                saw_addr = true;
            }
            "--count" => {
                let n: usize = match v.parse() {
                    Ok(n) => n,
                    Err(_) => fail("bad_argument", "count is not a number"),
                };
                if n == 0 || n > 4096 {
                    fail("bad_argument", "count must be between 1 and 4096");
                }
                a.count = n;
            }
            other => fail("bad_argument", &format!("unknown option {}", other)),
        }
        i += 2;
    }
    if a.image.is_none() {
        fail("bad_argument", "--image is required");
    }
    if a.cmd == "disasm" && !saw_addr {
        fail("bad_argument", "disasm requires --addr");
    }
    a
}

fn parse_u16(s: &str) -> u16 {
    let t = s.trim();
    let parsed = match t.strip_prefix("0x") {
        Some(hex) => u32::from_str_radix(hex, 16).ok(),
        None => t.parse::<u32>().ok(),
    };
    match parsed {
        Some(n) if n <= 0xFFFF => n as u16,
        _ => fail("bad_argument", &format!("{} is not a 16-bit address", s)),
    }
}

fn parse_hex(s: &str) -> Vec<u8> {
    let t = s.trim();
    if t.len() % 2 != 0 {
        fail("bad_argument", "key hex string has an odd number of digits");
    }
    let b = t.as_bytes();
    let mut out = Vec::new();
    for c in b.chunks(2) {
        let pair = std::str::from_utf8(c).unwrap();
        match u8::from_str_radix(pair, 16) {
            Ok(v) => out.push(v),
            Err(_) => fail("bad_argument", &format!("{} is not hexadecimal", pair)),
        }
    }
    out
}

fn hexstr(b: &[u8]) -> String {
    b.iter().map(|x| format!("{:02x}", x)).collect()
}

fn addr_list(a: &[u16]) -> String {
    let parts: Vec<String> = a.iter().map(|x| format!("\"0x{:04x}\"", x)).collect();
    format!("[{}]", parts.join(","))
}

fn main() {
    let args = parse_args();
    let path = args.image.clone().unwrap();
    let raw = match std::fs::read(&path) {
        Ok(v) => v,
        Err(e) => fail("io_error", &format!("cannot read {}: {}", path, e)),
    };
    let fw = match image::parse(&raw) {
        Ok(f) => f,
        Err((c, d)) => fail(c, &d),
    };

    match args.cmd.as_str() {
        "disasm" => {
            let mem = if args.live {
                let mut m = Machine::new(&fw.body, &[]);
                m.run();
                m.mem
            } else {
                let mut mem = vec![0u8; 0x10000];
                mem[..fw.body.len()].copy_from_slice(&fw.body);
                mem
            };
            let mut pc = args.addr as u32;
            for _ in 0..args.count {
                let ins = decode::decode(&mem, (pc & 0xFFFF) as u16);
                println!("{}", decode::line(&ins));
                pc += ins.len as u32;
                if pc > 0xFFFF {
                    pc &= 0xFFFF;
                }
            }
        }
        "run" => {
            let mut m = Machine::new(&fw.body, &args.key);
            m.run();
            let fault = if m.verdict() == "fault" { "\"illegal_instruction\"" } else { "null" };
            let latch: Vec<String> = m.latch.iter().map(|b| format!("\"0x{:02x}\"", b)).collect();
            println!(
                "{{\"status\":\"{}\",\"fault\":{},\"halt_pc\":\"0x{:04x}\",\"instructions\":{},\"cycles\":{},\"key_reads\":{},\"latch\":[{}]}}",
                m.verdict(),
                fault,
                m.stop_pc,
                m.instructions,
                m.cycles,
                m.key_pos,
                latch.join(",")
            );
        }
        "map" => {
            let mut m = Machine::new(&fw.body, &[]);
            m.run();
            let mut ranges: Vec<(usize, usize)> = Vec::new();
            let mut i = 0usize;
            while i < fw.body.len() {
                if m.mem[i] != fw.body[i] {
                    let start = i;
                    while i < fw.body.len() && m.mem[i] != fw.body[i] {
                        i += 1;
                    }
                    ranges.push((start, i));
                } else {
                    i += 1;
                }
            }
            let rs: Vec<String> = ranges
                .iter()
                .map(|(s, e)| format!("{{\"start\":\"0x{:04x}\",\"end\":\"0x{:04x}\"}}", s, e))
                .collect();
            let entry = u16::from_be_bytes([fw.body[0], fw.body[1]]);
            println!(
                "{{\"entry\":\"0x{:04x}\",\"load\":\"0x{:04x}\",\"body_len\":{},\"checksum\":\"0x{:04x}\",\"patched\":[{}],\"io_reads\":{},\"io_writes\":{},\"status\":\"{}\",\"halt_pc\":\"0x{:04x}\",\"instructions\":{},\"cycles\":{}}}",
                entry,
                fw.load,
                fw.body.len(),
                fw.checksum,
                rs.join(","),
                addr_list(&m.io_reads),
                addr_list(&m.io_writes),
                m.verdict(),
                m.stop_pc,
                m.instructions,
                m.cycles
            );
        }
        "recover" => match recover::recover(&fw.body) {
            Some(code) => {
                let printable = code.iter().all(|b| (0x20..=0x7E).contains(b));
                let text = if printable {
                    format!("\"{}\"", escape(&String::from_utf8_lossy(&code)))
                } else {
                    "null".to_string()
                };
                println!(
                    "{{\"length\":{},\"code_hex\":\"{}\",\"code_text\":{}}}",
                    code.len(),
                    hexstr(&code),
                    text
                );
            }
            None => fail("unrecoverable", "no accepted key stream could be reconstructed"),
        },
        _ => unreachable!(),
    }
}
