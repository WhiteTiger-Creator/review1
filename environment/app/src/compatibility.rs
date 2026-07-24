//! API and database compatibility checks.
//! Revision, method, content-type, and status matching are intentionally incomplete.

#![allow(dead_code)]

use crate::model::ApiOperation;

/// Returns true when an operation id string is nonempty. Does not validate revisions.
pub fn operation_id_present(op: &ApiOperation) -> bool {
    !op.operation_id.is_empty()
}
