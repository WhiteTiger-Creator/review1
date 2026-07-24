use std::path::PathBuf;

use clap::Parser;

#[derive(Debug, Parser)]
#[command(name = "vault-maze-lock")]
pub struct Cli {
    #[arg(long)]
    pub runbooks: PathBuf,

    #[arg(long)]
    pub release_config: PathBuf,

    #[arg(long)]
    pub api_contract: PathBuf,

    #[arg(long)]
    pub database: PathBuf,

    #[arg(long)]
    pub requests: PathBuf,

    #[arg(long)]
    pub output: PathBuf,
}
