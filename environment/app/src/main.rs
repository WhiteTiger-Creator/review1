#![allow(dead_code)]
#![allow(clippy::too_many_arguments)]
#![allow(clippy::if_same_then_else)]
#![allow(clippy::needless_borrows_for_generic_args)]

mod batching;
mod capabilities;
mod checksum;
mod cli;
mod compatibility;
mod error;
mod graph;
mod input;
mod model;
mod output;
mod replacement;
mod report;

use std::process::ExitCode;

use clap::Parser;

use crate::cli::Cli;
use crate::error::FatalInputError;
use crate::input::load_inputs;
use crate::output::{remove_stale_output, serialize_report, write_report_atomic};
use crate::report::plan_all;

fn main() -> ExitCode {
    let cli = Cli::parse();
    match run(&cli) {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("{err}");
            remove_stale_output(&cli.output);
            ExitCode::FAILURE
        }
    }
}

fn run(cli: &Cli) -> Result<(), FatalInputError> {
    let inputs = load_inputs(
        &cli.runbooks,
        &cli.release_config,
        &cli.api_contract,
        &cli.database,
        &cli.requests,
    )?;
    let report = plan_all(&inputs);
    let content = serialize_report(&report);
    write_report_atomic(&cli.output, &content).map_err(|e| FatalInputError::new(e.to_string()))?;
    Ok(())
}
