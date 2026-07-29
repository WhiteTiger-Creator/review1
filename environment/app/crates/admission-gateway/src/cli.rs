use std::path::PathBuf;

use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "admission-gateway")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    Evaluate {
        #[arg(long)]
        request: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    Inspect {
        #[arg(long, group = "inspect_target")]
        request: Option<PathBuf>,
        #[arg(long, group = "inspect_target")]
        evidence: Option<PathBuf>,
    },
    Verify {
        #[arg(long)]
        request: PathBuf,
        #[arg(long)]
        decision: PathBuf,
        #[arg(long)]
        evidence: PathBuf,
    },
}
