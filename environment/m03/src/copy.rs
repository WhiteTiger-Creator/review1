use rusqlite::{Connection, params};
use m01_seal::{VaultConfig, VaultError, check_failpoint};

use crate::journal::Journal;

pub struct CopyPlanner;

impl CopyPlanner {
    pub fn reserve_batch(
        conn: &mut Connection,
        upgrade_id: &str,
        target: i64,
        config: &VaultConfig,
    ) -> Result<(), VaultError> {
        let batch = 0i64;
        for slot in 0..config.batch_size as i64 {
            let nonce = m02_cipher::allocate_nonce(&config.active_key_id, target, batch, slot);
            conn.execute(
                "INSERT INTO nonce_reservations (upgrade_id, batch_number, slot, key_id, nonce, consumed)
                 VALUES (?1, ?2, ?3, ?4, ?5, 0)",
                params![upgrade_id, batch, slot, config.active_key_id, nonce],
            )?;
        }
        Journal::set_batch(conn, upgrade_id, batch)?;
        Journal::set_phase(conn, upgrade_id, m01_seal::UpgradePhase::Copying)?;
        Ok(())
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
        let batch: i64 = conn.query_row(
            "SELECT reservation_batch FROM upgrade_journal WHERE upgrade_id = ?1",
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

        let batch_size = config.batch_size as i64;
        while (cursor as usize) < records.len() {
            let end = std::cmp::min(cursor + batch_size, records.len() as i64);
            let tx = conn.unchecked_transaction()?;
            let mut slot = 0i64;
            for idx in cursor..end {
                let (record_id, key_id, epoch, counter, _old_nonce, ciphertext) = &records[idx as usize];
                let exists: i64 = tx.query_row(
                    "SELECT COUNT(*) FROM records
                     WHERE record_id = ?1 AND generation_id = ?2 AND version_epoch = ?3 AND version_counter = ?4",
                    params![record_id, target, epoch, counter],
                    |row| row.get(0),
                )?;
                if exists > 0 {
                    continue;
                }
                let nonce = m02_cipher::allocate_nonce(&config.active_key_id, target, batch, slot);
                tx.execute(
                    "INSERT INTO records (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
                    params![record_id, target, key_id, nonce, ciphertext, epoch, counter],
                )?;
                tx.execute(
                    "UPDATE nonce_reservations SET record_id = ?1, consumed = 1
                     WHERE upgrade_id = ?2 AND batch_number = ?3 AND slot = ?4",
                    params![record_id, upgrade_id, batch, slot],
                )?;
                slot += 1;
                if check_failpoint("after-partial-copy").is_err() {
                    tx.commit()?;
                    std::process::exit(m01_seal::FAILPOINT_EXIT_CODE);
                }
            }
            tx.commit()?;
            Self::advance_a(conn, upgrade_id, end)?;
            cursor = end;
        }
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
