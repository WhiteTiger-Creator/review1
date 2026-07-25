//! Report publication (starter incomplete for durable replacement).

use crate::diagnostic::failure::{fail, AppResult, FailureCode};
use crate::report::calibration_record::CalibrationRecord;
use std::path::Path;

pub fn publish_record(_report_path: &Path, _rec: &CalibrationRecord) -> AppResult<()> {
    fail(
        FailureCode::EReport,
        "atomic report publication unavailable",
    )
}

pub fn publish_bytes(_report_path: &Path, _bytes: &[u8]) -> AppResult<()> {
    fail(
        FailureCode::EReport,
        "atomic report publication unavailable",
    )
}

pub fn preserve_on_failure(_report_path: &Path) {}

pub fn unavailable_calibrate() -> AppResult<()> {
    fail(
        FailureCode::EOptimization,
        "calibration workflow unavailable in this build",
    )
}
