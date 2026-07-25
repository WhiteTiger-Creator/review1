use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Debug, Parser)]
#[command(
    name = "cmake-reconciler",
    about = "CMake-inspired FetchContent and provider lock reconciler"
)]
pub struct Args {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    /// Reconcile dependency requests and emit a resolution report.
    Reconcile {
        #[arg(long)]
        data_dir: PathBuf,
        #[arg(long)]
        report_out: PathBuf,
    },
}
