use rusqlite::{Connection, params};
use uuid::Uuid;
use m01_seal::{PinSummary, ReaderSnapshot, VaultError};

use crate::catalog::Catalog;

pub struct PinManager;

impl PinManager {
    pub fn open_reader(conn: &mut Connection, session_id: &str) -> Result<ReaderSnapshot, VaultError> {
        let generation_id = Catalog::published_generation(conn)?;
        let token = format!("rdr_{}", Uuid::new_v4());
        let reader_id = format!("reader_{}", Uuid::new_v4());
        let lease_epoch: i64 = conn.query_row(
            "SELECT COALESCE(MAX(lease_epoch), 0) + 1 FROM reader_pins",
            [],
            |row| row.get(0),
        )?;
        let opened_seq: i64 = conn.query_row(
            "SELECT COALESCE(MAX(opened_seq), 0) + 1 FROM reader_pins",
            [],
            |row| row.get(0),
        )?;
        conn.execute(
            "INSERT INTO reader_pins (token, reader_id, generation_id, lease_epoch, opened_seq, released, session_id)
             VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6)",
            params![token, reader_id, generation_id, lease_epoch, opened_seq, session_id],
        )?;
        Ok(ReaderSnapshot {
            token,
            reader_id,
            generation_id: m01_seal::GenerationId(generation_id),
            lease_epoch: lease_epoch as u64,
            opened_seq: opened_seq as u64,
        })
    }

    pub fn generation_for_token(conn: &Connection, token: &str) -> Result<i64, VaultError> {
        conn.query_row(
            "SELECT generation_id FROM reader_pins WHERE token = ?1 AND released = 0",
            [token],
            |row| row.get(0),
        )
        .map_err(|_| VaultError::NotFound(format!("reader token {token}")))
    }

    pub fn close_reader(conn: &mut Connection, token: &str) -> Result<(), VaultError> {
        let updated = conn.execute(
            "UPDATE reader_pins SET released = 1 WHERE token = ?1",
            [token],
        )?;
        if updated == 0 {
            return Err(VaultError::NotFound(format!("reader token {token}")));
        }
        Ok(())
    }

    pub fn active_count(conn: &Connection) -> Result<usize, VaultError> {
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM reader_pins WHERE released = 0",
            [],
            |row| row.get(0),
        )?;
        Ok(count as usize)
    }

    pub fn list_pins(conn: &Connection) -> Result<Vec<PinSummary>, VaultError> {
        let mut stmt = conn.prepare(
            "SELECT token, reader_id, generation_id, released, lease_epoch FROM reader_pins ORDER BY opened_seq",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(PinSummary {
                token: row.get(0)?,
                reader_id: row.get(1)?,
                generation_id: row.get(2)?,
                released: row.get::<_, i64>(3)? != 0,
                lease_epoch: row.get::<_, i64>(4)? as u64,
            })
        })?;
        Ok(rows.collect::<Result<Vec<_>, _>>()?)
    }

    pub fn reconcile_pins(conn: &mut Connection, session_id: &str, target: i64) -> Result<(), VaultError> {
        Self::hold_d(conn, session_id, target)?;
        crate::catalog::Catalog::set_state(conn, target, m01_seal::GenerationState::PinsReconciled)
    }

    fn hold_d(conn: &mut Connection, session_id: &str, target: i64) -> Result<(), VaultError> {
        conn.execute(
            "UPDATE reader_pins SET released = 1
             WHERE released = 0 AND (session_id IS NULL OR session_id != ?1)",
            [session_id],
        )?;
        conn.execute(
            "UPDATE reader_pins SET generation_id = ?1
             WHERE released = 0 AND session_id = ?2",
            params![target, session_id],
        )?;
        Ok(())
    }
}
