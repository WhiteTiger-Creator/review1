use m01_seal::{JournalSummary, UpgradePhase, VaultError};
use rusqlite::{params, Connection};

pub struct Journal;

impl Journal {
    fn bump_updated_at(conn: &Connection, upgrade_id: &str) -> Result<(), VaultError> {
        conn.execute(
            "UPDATE upgrade_journal SET updated_at = datetime(
                (SELECT COALESCE(MAX(updated_at), datetime('now', '-1 second')) FROM upgrade_journal),
                '+1 second'
            ) WHERE upgrade_id = ?1",
            [upgrade_id],
        )?;
        Ok(())
    }

    pub fn begin(
        conn: &mut Connection,
        upgrade_id: &str,
        source: i64,
        target: i64,
    ) -> Result<(), VaultError> {
        conn.execute(
            "INSERT INTO upgrade_journal
             (upgrade_id, phase, source_generation_id, target_generation_id, copy_cursor, reservation_batch, last_action, updated_at)
             VALUES (?1, 'reserved', ?2, ?3, 0, 0, 'begin', '1970-01-01 00:00:00')",
            params![upgrade_id, source, target],
        )?;
        Self::bump_updated_at(conn, upgrade_id)?;
        Ok(())
    }

    pub fn set_phase(
        conn: &Connection,
        upgrade_id: &str,
        phase: UpgradePhase,
    ) -> Result<(), VaultError> {
        conn.execute(
            "UPDATE upgrade_journal SET phase = ?1 WHERE upgrade_id = ?2",
            params![phase.as_str(), upgrade_id],
        )?;
        Self::bump_updated_at(conn, upgrade_id)?;
        Ok(())
    }

    pub fn set_cursor(conn: &Connection, upgrade_id: &str, cursor: i64) -> Result<(), VaultError> {
        conn.execute(
            "UPDATE upgrade_journal SET copy_cursor = ?1 WHERE upgrade_id = ?2",
            params![cursor, upgrade_id],
        )?;
        Self::bump_updated_at(conn, upgrade_id)?;
        Ok(())
    }

    pub fn set_batch(conn: &Connection, upgrade_id: &str, batch: i64) -> Result<(), VaultError> {
        conn.execute(
            "UPDATE upgrade_journal SET reservation_batch = ?1 WHERE upgrade_id = ?2",
            params![batch, upgrade_id],
        )?;
        Self::bump_updated_at(conn, upgrade_id)?;
        Ok(())
    }

    pub fn complete(conn: &Connection, upgrade_id: &str) -> Result<(), VaultError> {
        Self::set_phase(conn, upgrade_id, UpgradePhase::Complete)
    }

    pub fn active_upgrade(conn: &Connection) -> Result<Option<(String, UpgradePhase)>, VaultError> {
        let result = conn.query_row(
            "SELECT upgrade_id, phase FROM upgrade_journal
             WHERE phase NOT IN ('complete', 'idle')
             ORDER BY updated_at DESC LIMIT 1",
            [],
            |row| {
                let phase_str: String = row.get(1)?;
                Ok((
                    row.get::<_, String>(0)?,
                    UpgradePhase::parse(&phase_str).unwrap_or(UpgradePhase::Idle),
                ))
            },
        );
        match result {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    pub fn read_summary(conn: &Connection) -> Result<Option<JournalSummary>, VaultError> {
        let result = conn.query_row(
            "SELECT upgrade_id, phase, source_generation_id, target_generation_id, copy_cursor, reservation_batch
             FROM upgrade_journal ORDER BY updated_at DESC LIMIT 1",
            [],
            |row| {
                let phase_str: String = row.get(1)?;
                Ok(JournalSummary {
                    upgrade_id: row.get(0)?,
                    phase: UpgradePhase::parse(&phase_str).unwrap_or(UpgradePhase::Idle),
                    source_generation_id: row.get(2)?,
                    target_generation_id: row.get(3)?,
                    copy_cursor: row.get(4)?,
                    reservation_batch: row.get(5)?,
                })
            },
        );
        match result {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }

    pub fn read_for_recover(
        conn: &Connection,
    ) -> Result<Option<(String, UpgradePhase, i64, i64, i64, i64)>, VaultError> {
        let result = conn.query_row(
            "SELECT upgrade_id, phase, source_generation_id, target_generation_id, copy_cursor, reservation_batch
             FROM upgrade_journal WHERE phase NOT IN ('complete') ORDER BY updated_at DESC LIMIT 1",
            [],
            |row| {
                let phase_str: String = row.get(1)?;
                Ok((
                    row.get(0)?,
                    UpgradePhase::parse(&phase_str).unwrap_or(UpgradePhase::Idle),
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                ))
            },
        );
        match result {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e.into()),
        }
    }
}
