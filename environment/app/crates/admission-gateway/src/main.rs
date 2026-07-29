mod cli;
mod commands;

use anyhow::Result;
use clap::Parser;
use cli::Cli;

fn main() -> Result<()> {
    let cli = Cli::parse();
    commands::dispatch(cli)
}
