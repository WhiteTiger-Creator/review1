use clap::Parser;
use std::process::ExitCode;

mod canonical;
mod cli;
mod error;
mod loader;
mod models;
mod output;
mod reconcile;
mod version;

use crate::cli::{Args, Command};
use crate::error::FatalError;
use crate::output::{atomic_write, remove_stale_output};

fn main() -> ExitCode {
    let args = Args::parse();
    match args.command {
        Command::Reconcile {
            data_dir,
            report_out,
        } => match run_reconcile(&data_dir, &report_out) {
            Ok(()) => ExitCode::SUCCESS,
            Err(err) => {
                let _ = remove_stale_output(&report_out);
                eprintln!("{err}");
                ExitCode::FAILURE
            }
        },
    }
}

fn run_reconcile(
    data_dir: &std::path::Path,
    report_out: &std::path::Path,
) -> Result<(), FatalError> {
    let report = reconcile::reconcile(data_dir)?;
    let bytes = crate::canonical::pretty_json(&report).map_err(|err| {
        FatalError::new(crate::error::OUTPUT_WRITE_FAILED, err.to_string())
    })?;
    atomic_write(report_out, &bytes)?;
    Ok(())
}

#[allow(dead_code)]
fn _starter_module_anchor() {
    let _ = std::any::type_name::<FatalError>();
}
