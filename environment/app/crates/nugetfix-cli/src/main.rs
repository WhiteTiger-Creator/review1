fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(|s| s.as_str()) == Some("--version") {
        println!("nugetfix 0.12.0");
        return;
    }
    eprintln!("nugetfix stub: implement audit per /app/docs/audit-contract.md");
    std::process::exit(2);
}
