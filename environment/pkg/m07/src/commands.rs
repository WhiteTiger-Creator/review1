use anyhow::Result;
use m05::{GcEngine, GcInterrupt};
use m06::{RecoveryEngine, RecoveryInterrupt};

pub fn recover(root: &str, output: &str, interrupt: Option<RecoveryInterrupt>) -> Result<()> {
    RecoveryEngine::new(root).recover(std::path::Path::new(output), interrupt)?;
    Ok(())
}

pub fn gc(root: &str, interrupt: Option<GcInterrupt>) -> Result<()> {
    let _report = GcEngine::new(root).run(interrupt)?;
    Ok(())
}

pub fn verify_store(root: &str) -> Result<()> {
    RecoveryEngine::new(root).verify_store()
}
