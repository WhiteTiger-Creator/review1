//! Reconciliation orchestration (candidate starter — not implemented).

use crate::error::{FatalError, NOT_IMPLEMENTED};
use crate::loader::{load_data_dir, required_files_exist};
use crate::models::Report;
use std::path::Path;

pub fn reconcile(data_dir: &Path) -> Result<Report, FatalError> {
    required_files_exist(data_dir)?;
    let _data = load_data_dir(data_dir)?;
    Err(FatalError::new(
        NOT_IMPLEMENTED,
        "reconciliation logic is not implemented",
    ))
}
