use std::collections::HashSet;

use m01_seal::{GenerationState, VaultError};
use rusqlite::{params, Connection};

use crate::catalog::Catalog;
use crate::journal::Journal;

pub struct Publisher;

impl Publisher {
    pub fn publish(conn: &mut Connection, upgrade_id: &str, target: i64) -> Result<(), VaultError> {
        Self::validate_target(conn, upgrade_id, target)?;
        Self::mark_c(conn, target)?;
        Journal::set_phase(conn, upgrade_id, m01_seal::UpgradePhase::Published)?;
        Ok(())
    }

    fn mark_c(conn: &Connection, target: i64) -> Result<(), VaultError> {
        Catalog::set_state(conn, target, GenerationState::Published)
    }

    pub fn validate_committed_accounting(
        conn: &Connection,
        upgrade_id: &str,
        target: i64,
    ) -> Result<(), VaultError> {
        Self::reject_duplicate_target_nonces(conn, target)?;

        let row_keys = Self::target_row_keys(conn, target)?;
        let reservation_keys = Self::consumed_reservation_keys(conn, upgrade_id)?;

        if row_keys != reservation_keys {
            return Err(VaultError::InvalidState(
                "committed rows and consumed reservations mismatch".into(),
            ));
        }

        let bad_unconsumed: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nonce_reservations
             WHERE upgrade_id = ?1 AND consumed = 0 AND record_id IS NOT NULL",
            [upgrade_id],
            |row| row.get(0),
        )?;
        if bad_unconsumed > 0 {
            return Err(VaultError::InvalidState(
                "unconsumed reservation names a committed record".into(),
            ));
        }

        let coord_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM (
                SELECT batch_number, slot FROM nonce_reservations
                WHERE upgrade_id = ?1 AND consumed = 1
            )",
            [upgrade_id],
            |row| row.get(0),
        )?;
        let consumed_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nonce_reservations
             WHERE upgrade_id = ?1 AND consumed = 1",
            [upgrade_id],
            |row| row.get(0),
        )?;
        if coord_count != consumed_count {
            return Err(VaultError::InvalidState(
                "consumed reservation coordinates must be unique".into(),
            ));
        }

        Ok(())
    }

    pub fn validate_target(
        conn: &Connection,
        upgrade_id: &str,
        target: i64,
    ) -> Result<(), VaultError> {
        let source: i64 = conn.query_row(
            "SELECT source_generation_id FROM upgrade_journal WHERE upgrade_id = ?1",
            [upgrade_id],
            |row| row.get(0),
        )?;

        let source_occurrences: i64 = conn.query_row(
            "SELECT COUNT(*) FROM records WHERE generation_id = ?1",
            [source],
            |row| row.get(0),
        )?;
        let target_occurrences: i64 = conn.query_row(
            "SELECT COUNT(*) FROM records WHERE generation_id = ?1",
            [target],
            |row| row.get(0),
        )?;
        if source_occurrences != target_occurrences {
            return Err(VaultError::InvalidState(
                "target occurrence count mismatch".into(),
            ));
        }

        let missing: i64 = conn.query_row(
            "SELECT COUNT(*) FROM records AS s
             WHERE s.generation_id = ?1
               AND NOT EXISTS (
                 SELECT 1 FROM records AS t
                 WHERE t.generation_id = ?2
                   AND t.record_id = s.record_id
                   AND t.version_epoch = s.version_epoch
                   AND t.version_counter = s.version_counter
               )",
            params![source, target],
            |row| row.get(0),
        )?;
        if missing > 0 {
            return Err(VaultError::InvalidState(
                "missing compatible target occurrences".into(),
            ));
        }

        Self::validate_committed_accounting(conn, upgrade_id, target)?;

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

    fn reject_duplicate_target_nonces(conn: &Connection, target: i64) -> Result<(), VaultError> {
        let dup: i64 = conn.query_row(
            "SELECT COUNT(*) FROM (
                SELECT 1 FROM records WHERE generation_id = ?1
                GROUP BY key_id, nonce HAVING COUNT(*) > 1
             )",
            [target],
            |row| row.get(0),
        )?;
        if dup > 0 {
            return Err(VaultError::InvalidState(
                "duplicate committed nonce in target".into(),
            ));
        }
        Ok(())
    }

    fn target_row_keys(conn: &Connection, target: i64) -> Result<HashSet<(String, String, String)>, VaultError> {
        let mut stmt = conn.prepare(
            "SELECT record_id, key_id, nonce FROM records WHERE generation_id = ?1",
        )?;
        let rows = stmt.query_map([target], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?))
        })?;
        rows.collect::<Result<HashSet<_>, _>>()
            .map_err(VaultError::from)
    }

    fn consumed_reservation_keys(
        conn: &Connection,
        upgrade_id: &str,
    ) -> Result<HashSet<(String, String, String)>, VaultError> {
        let mut stmt = conn.prepare(
            "SELECT record_id, key_id, nonce FROM nonce_reservations
             WHERE upgrade_id = ?1 AND consumed = 1 AND record_id IS NOT NULL",
        )?;
        let rows = stmt.query_map([upgrade_id], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?))
        })?;
        rows.collect::<Result<HashSet<_>, _>>()
            .map_err(VaultError::from)
    }
}
