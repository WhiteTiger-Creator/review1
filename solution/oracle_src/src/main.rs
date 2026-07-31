use std::io::{stderr, Write};
use std::process::ExitCode;

use webauthn_assertion_worker::cli::parse_args;
use webauthn_assertion_worker::output::cleanup_outputs;
use webauthn_assertion_worker::run_worker;

fn main() -> ExitCode {
    let args = match parse_args(std::env::args_os()) {
        Ok(a) => a,
        Err(e) => {
            let _ = writeln!(stderr(), "fatal: {e}");
            return ExitCode::FAILURE;
        }
    };
    match run_worker(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            let _ = cleanup_outputs(&args.output);
            let _ = writeln!(stderr(), "fatal: {e:#}");
            ExitCode::FAILURE
        }
    }
}
