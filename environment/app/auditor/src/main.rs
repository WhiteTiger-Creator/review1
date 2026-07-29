use std::fs;
use std::path::PathBuf;
use std::process;

mod cli;
mod error;
mod report;

fn main() {
    let args = match cli::parse_args(std::env::args().skip(1).collect()) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("fatal: {e}");
            process::exit(1);
        }
    };
    if let Err(e) = run(args) {
        eprintln!("fatal: {e}");
        process::exit(1);
    }
}

pub struct Args {
    pub fixture_root: PathBuf,
    pub requests: PathBuf,
    pub environment_overrides: PathBuf,
    pub cli_overrides: PathBuf,
    pub source_profiles: PathBuf,
    pub solver_config: PathBuf,
    pub output: PathBuf,
}

fn run(args: Args) -> Result<(), error::AuditorError> {
    let tmp_sibling = PathBuf::from(format!("{}.tmp", args.output.display()));
    if args.output.exists() {
        fs::remove_file(&args.output).map_err(|e| error::AuditorError::Io(args.output.clone(), e))?;
    }
    if tmp_sibling.exists() {
        fs::remove_file(&tmp_sibling).map_err(|e| error::AuditorError::Io(tmp_sibling.clone(), e))?;
    }
    let _ = (
        args.fixture_root,
        args.requests,
        args.environment_overrides,
        args.cli_overrides,
        args.source_profiles,
        args.solver_config,
    );
    Err(error::AuditorError::Fatal(
        "auditor logic not implemented: reconstruct Cargo hierarchical configuration, includes, overrides, source replacement, integrity, lock reconciliation, and locked offline builds".into(),
    ))
}
