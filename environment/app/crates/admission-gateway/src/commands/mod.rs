use anyhow::Result;

use crate::cli::{Cli, Command};

mod evaluate;
mod inspect;
mod verify;

pub fn dispatch(cli: Cli) -> Result<()> {
    match cli.command {
        Command::Evaluate { request, output } => evaluate::run(request, output),
        Command::Inspect { request, evidence } => inspect::run(request, evidence),
        Command::Verify {
            request,
            decision,
            evidence,
        } => verify::run(request, decision, evidence),
    }
}
