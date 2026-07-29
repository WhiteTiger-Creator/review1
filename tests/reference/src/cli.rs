use crate::error::AuditorError;
use crate::Args;
use std::path::PathBuf;

pub fn parse_args(args: Vec<String>) -> Result<Args, AuditorError> {
    let mut fixture_root = None;
    let mut requests = None;
    let mut environment_overrides = None;
    let mut cli_overrides = None;
    let mut source_profiles = None;
    let mut solver_config = None;
    let mut output = None;

    let mut i = 0;
    while i < args.len() {
        let key = args[i].as_str();
        let val = args
            .get(i + 1)
            .ok_or_else(|| AuditorError::Fatal(format!("missing value for {key}")))?;
        match key {
            "--fixture-root" => fixture_root = Some(PathBuf::from(val)),
            "--requests" => requests = Some(PathBuf::from(val)),
            "--environment-overrides" => environment_overrides = Some(PathBuf::from(val)),
            "--cli-overrides" => cli_overrides = Some(PathBuf::from(val)),
            "--source-profiles" => source_profiles = Some(PathBuf::from(val)),
            "--solver-config" => solver_config = Some(PathBuf::from(val)),
            "--output" => output = Some(PathBuf::from(val)),
            other => {
                return Err(AuditorError::Fatal(format!("unknown argument: {other}")));
            }
        }
        i += 2;
    }

    Ok(Args {
        fixture_root: fixture_root
            .ok_or_else(|| AuditorError::Fatal("missing --fixture-root".into()))?,
        requests: requests.ok_or_else(|| AuditorError::Fatal("missing --requests".into()))?,
        environment_overrides: environment_overrides
            .ok_or_else(|| AuditorError::Fatal("missing --environment-overrides".into()))?,
        cli_overrides: cli_overrides
            .ok_or_else(|| AuditorError::Fatal("missing --cli-overrides".into()))?,
        source_profiles: source_profiles
            .ok_or_else(|| AuditorError::Fatal("missing --source-profiles".into()))?,
        solver_config: solver_config
            .ok_or_else(|| AuditorError::Fatal("missing --solver-config".into()))?,
        output: output.ok_or_else(|| AuditorError::Fatal("missing --output".into()))?,
    })
}
