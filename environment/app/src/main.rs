use std::io::{self, Read, Write};

mod repair;

// CLI plumbing for `rotctl`. Argument parsing, batch framing, and I/O all
// live here already; `repair.rs` owns the actual per-window computation.
// See docs/rotation-contract.md for the exact format this reads and writes.

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 || args[1] != "repair" {
        eprintln!("usage: rotctl repair < report.txt");
        std::process::exit(2);
    }

    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .expect("failed to read stdin");

    let mut tokens = input
        .split_ascii_whitespace()
        .map(|tok| tok.parse::<i64>().expect("malformed integer in input"));

    let window_count = tokens.next().expect("missing window count") as usize;

    let mut out = String::new();
    for _ in 0..window_count {
        let n = tokens.next().expect("missing slot count") as usize;
        let m = tokens.next().expect("missing batch size") as usize;
        let tags: Vec<u32> = (0..n)
            .map(|_| tokens.next().expect("missing slot tag") as u32)
            .collect();

        let (corrections, fixed) = repair::repair(n, m, &tags);

        out.push_str(&corrections.to_string());
        out.push('\n');
        let rendered: Vec<String> = fixed.iter().map(|v| v.to_string()).collect();
        out.push_str(&rendered.join(" "));
        out.push('\n');
    }

    io::stdout()
        .write_all(out.as_bytes())
        .expect("failed to write stdout");
}
