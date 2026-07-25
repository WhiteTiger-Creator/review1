//! Command-line argument parsing for modal-reconciler.

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use std::path::PathBuf;

#[derive(Debug)]
pub enum Command {
    Help,
    Spectrum { model: PathBuf },
    Calibrate {
        model: PathBuf,
        survey: PathBuf,
        plan: PathBuf,
        report: PathBuf,
    },
}

pub fn parse(args: &[String]) -> AppResult<Command> {
    if args.len() <= 1 || args.iter().any(|a| a == "--help" || a == "-h") {
        return Ok(Command::Help);
    }
    let cmd = args[1].as_str();
    match cmd {
        "spectrum" => {
            let model = required_path(args, "--model")?;
            Ok(Command::Spectrum { model })
        }
        "calibrate" => {
            let model = required_path(args, "--model")?;
            let survey = required_path(args, "--survey")?;
            let plan = required_path(args, "--plan")?;
            let report = required_path(args, "--report")?;
            Ok(Command::Calibrate {
                model,
                survey,
                plan,
                report,
            })
        }
        _ => fail(FailureCode::EPath, format!("unknown command {cmd}")),
    }
}

fn required_path(args: &[String], flag: &str) -> AppResult<PathBuf> {
    let mut i = 2usize;
    while i < args.len() {
        if args[i] == flag {
            if i + 1 >= args.len() {
                return fail(FailureCode::EPath, format!("missing value for {flag}"));
            }
            return Ok(PathBuf::from(&args[i + 1]));
        }
        i += 1;
    }
    fail(FailureCode::EPath, format!("missing {flag}"))
}

pub fn print_help() {
    println!("modal-reconciler — bridge modal spectrum and stiffness calibration");
    println!();
    println!("Usage:");
    println!("  modal-reconciler spectrum --model <path>");
    println!("  modal-reconciler calibrate --model <path> --survey <path> --plan <path> --report <path>");
    println!("  modal-reconciler --help");
}
