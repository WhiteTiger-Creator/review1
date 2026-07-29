use rusqlite::{Connection, params};
use m01_seal::{GenerationState, VaultError};

use crate::catalog::Catalog;
use crate::journal::Journal;

pub struct Publisher;

impl Publisher {
    pub fn publish(conn: &mut Connection, upgrade_id: &str, target: i64) -> Result<(), VaultError> {
        Self::mark_c(conn, target)?;
        let unconsumed: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nonce_reservations
             WHERE upgrade_id = ?1 AND consumed = 0",
            [upgrade_id],
            |row| row.get(0),
        )?;
        if unconsumed > 0 {
            return Err(VaultError::InvalidState(format!(
                "{unconsumed} unconsumed nonce reservations"
            )));
        }
        Journal::set_phase(conn, upgrade_id, m01_seal::UpgradePhase::Published)?;
        Ok(())
    }

    fn mark_c(conn: &Connection, target: i64) -> Result<(), VaultError> {
        Catalog::set_state(conn, target, GenerationState::Published)
    }

    pub fn validate_target(conn: &Connection, upgrade_id: &str, target: i64) -> Result<(), VaultError> {
        let source: i64 = conn.query_row(
            "SELECT source_generation_id FROM upgrade_journal WHERE upgrade_id = ?1",
            [upgrade_id],
            |row| row.get(0),
        )?;
        let source_count: i64 = conn.query_row(
            "SELECT COUNT(DISTINCT record_id) FROM records WHERE generation_id = ?1",
            [source],
            |row| row.get(0),
        )?;
        let target_count: i64 = conn.query_row(
            "SELECT COUNT(DISTINCT record_id) FROM records WHERE generation_id = ?1",
            [target],
            |row| row.get(0),
        )?;
        if source_count != target_count {
            return Err(VaultError::InvalidState("target record count mismatch".into()));
        }
        let unconsumed: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nonce_reservations
             WHERE upgrade_id = ?1 AND consumed = 0",
            [upgrade_id],
            |row| row.get(0),
        )?;
        if unconsumed > 0 {
            return Err(VaultError::InvalidState(format!(
                "{unconsumed} unconsumed nonce reservations"
            )));
        }
        Journal::set_phase(conn, upgrade_id, m01_seal::UpgradePhase::Validated)?;
        Catalog::set_state(conn, target, GenerationState::Validated)?;
        Ok(())
    }
}
