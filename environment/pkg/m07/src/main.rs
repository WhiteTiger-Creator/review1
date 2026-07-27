mod commands;
mod import_bundle;
mod inspect;
mod launch;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "rstore-cli", about = "OCI rstore maintenance CLI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Inspect {
        #[arg(long)]
        root: String,
    },
    Recover {
        #[arg(long)]
        root: String,
        #[arg(long)]
        output: String,
        #[arg(long, value_enum)]
        interrupt_after: Option<m06::RecoveryInterruptArg>,
    },
    RunImage {
        #[arg(long)]
        root: String,
        #[arg(long)]
        image: String,
        #[arg(long)]
        result: String,
    },
    Gc {
        #[arg(long)]
        root: String,
        #[arg(long, value_enum)]
        interrupt_after: Option<m05::GcInterruptArg>,
    },
    Import {
        #[arg(long)]
        root: String,
        #[arg(long)]
        bundle: String,
    },
    VerifyStore {
        #[arg(long)]
        root: String,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Inspect { root } => inspect::run(&root),
        Commands::Recover {
            root,
            output,
            interrupt_after,
        } => commands::recover(&root, &output, interrupt_after.map(Into::into)),
        Commands::RunImage { root, image, result } => launch::run(&root, &image, &result),
        Commands::Gc {
            root,
            interrupt_after,
        } => commands::gc(&root, interrupt_after.map(Into::into)),
        Commands::Import { root, bundle } => import_bundle::run(&root, &bundle),
        Commands::VerifyStore { root } => commands::verify_store(&root),
    }
}
