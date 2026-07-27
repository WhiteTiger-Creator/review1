use rusqlite::{Connection, params};
use m01_seal::{
    GenerationState, GenerationStatus, InspectReport, JournalSummary, PinSummary, RecordVersion,
    StatusReport, UpgradePhase, VaultError,
};

use crate::journal::Journal;
use crate::pins::PinManager;

pub struct Catalog;

impl Catalog {
    pub fn current_generation(conn: &Connection) -> Result<i64, VaultError> {
        conn.query_row(
            "SELECT generation_id FROM generation_catalog
             WHERE state IN ('published', 'pins_reconciled', 'cleanup_pending', 'complete')
             ORDER BY generation_id DESC LIMIT 1",
            [],
            |row| row.get(0),
        )
        .map_err(|_| VaultError::InvalidState("no published generation".into()))
    }

    pub fn published_generation(conn: &Connection) -> Result<i64, VaultError> {
        Self::current_generation(conn)
    }

    pub fn create_target_generation(conn: &mut Connection, key_id: &str) -> Result<i64, VaultError> {
        let next: i64 = conn.query_row(
            "SELECT COALESCE(MAX(generation_id), 0) + 1 FROM generation_catalog",
            [],
            |row| row.get(0),
        )?;
        let tx = conn.unchecked_transaction()?;
        tx.execute(
            "INSERT INTO generation_catalog (generation_id, state, key_id, schema_version, created_at)
             VALUES (?1, 'copying', ?2, 3, datetime('now'))",
            params![next, key_id],
        )?;
        tx.commit()?;
        Ok(next)
    }

    pub fn set_state(conn: &Connection, generation_id: i64, state: GenerationState) -> Result<(), VaultError> {
        conn.execute(
            "UPDATE generation_catalog SET state = ?1 WHERE generation_id = ?2",
            params![state.as_str(), generation_id],
        )?;
        Ok(())
    }

    pub fn mark_cleanup_pending(conn: &mut Connection, generation_id: i64) -> Result<(), VaultError> {
        Self::set_state(conn, generation_id, GenerationState::CleanupPending)
    }

    pub fn next_record_version(
        conn: &Connection,
        record_id: &str,
        generation_id: i64,
    ) -> Result<RecordVersion, VaultError> {
        let (epoch, counter): (i64, i64) = conn
            .query_row(
                "SELECT COALESCE(MAX(version_epoch), 0), COALESCE(MAX(version_counter), 0)
                 FROM records WHERE record_id = ?1 AND generation_id = ?2",
                params![record_id, generation_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap_or((0, 0));
        Ok(RecordVersion::new(epoch as u64, (counter + 1) as u64))
    }

    pub fn flag_h(conn: &Connection, generation_id: i64) -> bool {
        let state: String = conn
            .query_row(
                "SELECT state FROM generation_catalog WHERE generation_id = ?1",
                [generation_id],
                |row| row.get(0),
            )
            .unwrap_or_default();
        matches!(
            state.as_str(),
            "published" | "pins_reconciled" | "cleanup_pending" | "complete"
        )
    }

    pub fn is_reconciled(conn: &Connection, generation_id: i64) -> bool {
        let state: String = conn
            .query_row(
                "SELECT state FROM generation_catalog WHERE generation_id = ?1",
                [generation_id],
                |row| row.get(0),
            )
            .unwrap_or_default();
        matches!(
            state.as_str(),
            "pins_reconciled" | "cleanup_pending" | "complete"
        )
    }

    pub fn status_report(conn: &Connection, database_path: &str) -> Result<StatusReport, VaultError> {
        let schema_version = crate::schema::Schema::schema_version(conn)?;
        let published = Self::published_generation(conn).ok();
        let (upgrade_id, phase) = Journal::active_upgrade(conn)?
            .map(|(id, p)| (Some(id), p))
            .unwrap_or((None, UpgradePhase::Idle));
        let generations = Self::list_generations(conn)?;
        Ok(StatusReport {
            database_path: database_path.to_string(),
            schema_version,
            current_generation: published.map(m01_seal::GenerationId),
            published_generation: published.map(m01_seal::GenerationId),
            upgrade_phase: phase,
            upgrade_id,
            active_reader_count: PinManager::active_count(conn)?,
            generation_states: generations,
        })
    }

    pub fn inspect_report(conn: &Connection) -> Result<InspectReport, VaultError> {
        let generations = Self::list_generations(conn)?;
        let journal = Journal::read_summary(conn)?;
        let pins = PinManager::list_pins(conn)?;
        let nonce_reservation_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nonce_reservations",
            [],
            |row| row.get(0),
        )?;
        Ok(InspectReport {
            generations,
            journal,
            pins,
            nonce_reservation_count: nonce_reservation_count as usize,
        })
    }

    fn list_generations(conn: &Connection) -> Result<Vec<GenerationStatus>, VaultError> {
        let mut stmt = conn.prepare(
            "SELECT g.generation_id, g.state, g.key_id,
                    (SELECT COUNT(*) FROM records r WHERE r.generation_id = g.generation_id) AS cnt
             FROM generation_catalog g ORDER BY g.generation_id",
        )?;
        let rows = stmt.query_map([], |row| {
            let state_str: String = row.get(1)?;
            Ok(GenerationStatus {
                generation_id: row.get(0)?,
                state: GenerationState::parse(&state_str).unwrap_or(GenerationState::Copying),
                key_id: row.get(2)?,
                record_count: row.get::<_, i64>(3)? as usize,
            })
        })?;
        Ok(rows.collect::<Result<Vec<_>, _>>()?)
    }
}
