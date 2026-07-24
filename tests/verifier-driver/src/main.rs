mod cases;
mod harness;
mod reachability;
mod store_builder;

use anyhow::Result;

fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    match args.next().as_deref() {
        Some("materialize") => {
            let seed: u64 = args.next().expect("seed").parse()?;
            let root = args.next().expect("root");
            store_builder::materialize_store(seed, std::path::Path::new(&root))?;
        }
        _ => harness::run_all()?,
    }
    Ok(())
}
