use m01_seal::{check_failpoint, VaultConfig, VaultError};
use rusqlite::{params, Connection};

use crate::journal::Journal;

pub struct CopyPlanner;

impl CopyPlanner {
    pub fn reserve_batch(
        conn: &mut Connection,
        upgrade_id: &str,
        target: i64,
        config: &VaultConfig,
    ) -> Result<(), VaultError> {
        Self::ensure_batch(conn, upgrade_id, target, config, 0)
    }

    fn ensure_batch(
        conn: &mut Connection,
        upgrade_id: &str,
        target: i64,
        config: &VaultConfig,
        batch: i64,
    ) -> Result<(), VaultError> {
        let existing: i64 = conn.query_row(
            "SELECT COUNT(*) FROM nonce_reservations WHERE upgrade_id = ?1 AND batch_number = ?2",
            params![upgrade_id, batch],
            |row| row.get(0),
        )?;
        if existing > 0 {
            Journal::set_batch(conn, upgrade_id, batch)?;
            return Ok(());
        }
        for slot in 0..config.batch_size as i64 {
            let nonce = m02_cipher::allocate_nonce(&config.active_key_id, target, batch, slot);
            conn.execute(
                "INSERT INTO nonce_reservations (upgrade_id, batch_number, slot, key_id, nonce, consumed)
                 VALUES (?1, ?2, ?3, ?4, ?5, 0)",
                params![upgrade_id, batch, slot, config.active_key_id, nonce],
            )?;
        }
        Journal::set_batch(conn, upgrade_id, batch)?;
        Ok(())
    }

    fn take_slot(
        conn: &mut Connection,
        upgrade_id: &str,
        target: i64,
        config: &VaultConfig,
    ) -> Result<(String, i64, i64), VaultError> {
        let mut batch: i64 = conn.query_row(
            "SELECT reservation_batch FROM upgrade_journal WHERE upgrade_id = ?1",
            [upgrade_id],
            |row| row.get(0),
        )?;
        loop {
            if let Ok((nonce, slot)) = conn.query_row(
                "SELECT nonce, slot FROM nonce_reservations
                 WHERE upgrade_id = ?1 AND batch_number = ?2 AND consumed = 0
                 ORDER BY slot LIMIT 1",
                params![upgrade_id, batch],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?)),
            ) {
                return Ok((nonce, slot, batch));
            }
            batch += 1;
            Self::ensure_batch(conn, upgrade_id, target, config, batch)?;
        }
    }

    pub fn copy_batches(
        conn: &mut Connection,
        upgrade_id: &str,
        source: i64,
        target: i64,
        config: &VaultConfig,
    ) -> Result<(), VaultError> {
        let mut cursor: i64 = conn.query_row(
            "SELECT copy_cursor FROM upgrade_journal WHERE upgrade_id = ?1",
            [upgrade_id],
            |row| row.get(0),
        )?;

        let records: Vec<(String, String, i64, i64, String, Vec<u8>)> = {
            let mut stmt = conn.prepare(
                "SELECT record_id, key_id, version_epoch, version_counter, nonce, ciphertext
                 FROM records WHERE generation_id = ?1
                 ORDER BY record_id, version_epoch, version_counter",
            )?;
            let rows = stmt.query_map([source], |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                ))
            })?;
            rows.collect::<Result<Vec<_>, _>>()?
        };

        while (cursor as usize) < records.len() {
            let (record_id, key_id, epoch, counter, _old_nonce, ciphertext) =
                &records[cursor as usize];
            let exists: i64 = conn.query_row(
                "SELECT COUNT(*) FROM records
                 WHERE record_id = ?1 AND generation_id = ?2 AND version_epoch = ?3 AND version_counter = ?4",
                params![record_id, target, epoch, counter],
                |row| row.get(0),
            )?;
            if exists == 0 {
                let payload = m02_cipher::decrypt_payload(key_id, _old_nonce, ciphertext)?;
                let (nonce, slot, batch) = Self::take_slot(conn, upgrade_id, target, config)?;
                let new_ciphertext =
                    m02_cipher::encrypt_payload(&config.active_key_id, &nonce, &payload)?;
                let tx = conn.unchecked_transaction()?;
                tx.execute(
                    "INSERT INTO records (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
                    params![
                        record_id,
                        target,
                        &config.active_key_id,
                        nonce,
                        new_ciphertext,
                        epoch,
                        counter
                    ],
                )?;
                tx.execute(
                    "UPDATE nonce_reservations SET record_id = ?1, consumed = 1
                     WHERE upgrade_id = ?2 AND batch_number = ?3 AND slot = ?4",
                    params![record_id, upgrade_id, batch, slot],
                )?;
                tx.commit()?;
                if check_failpoint("after-partial-copy").is_err() {
                    Self::advance_a(conn, upgrade_id, cursor + 1)?;
                    std::process::exit(m01_seal::FAILPOINT_EXIT_CODE);
                }
            }
            cursor += 1;
            Self::advance_a(conn, upgrade_id, cursor)?;
        }
        conn.execute(
            "DELETE FROM nonce_reservations WHERE upgrade_id = ?1 AND consumed = 0",
            [upgrade_id],
        )?;
        Journal::set_phase(conn, upgrade_id, m01_seal::UpgradePhase::Copied)?;
        Ok(())
    }

    fn advance_a(conn: &Connection, upgrade_id: &str, new_cursor: i64) -> Result<(), VaultError> {
        Journal::set_cursor(conn, upgrade_id, new_cursor)
    }

    pub fn resume_copy(
        conn: &mut Connection,
        upgrade_id: &str,
        source: i64,
        target: i64,
        config: &VaultConfig,
    ) -> Result<(), VaultError> {
        Self::copy_batches(conn, upgrade_id, source, target, config)
    }
}
