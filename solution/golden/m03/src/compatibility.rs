use m01_seal::{LogicalRecord, RecordVersion, VaultError};
use rusqlite::{params, Connection};

use crate::catalog::Catalog;

pub struct CompatibilityView;

impl CompatibilityView {
    pub fn read_current(conn: &Connection, record_id: &str) -> Result<String, VaultError> {
        let published = Catalog::published_generation(conn)?;
        Self::view_f(conn, record_id, Some(published))
    }

    pub fn read_for_generation(
        conn: &Connection,
        generation_id: i64,
        record_id: &str,
    ) -> Result<String, VaultError> {
        let (key_id, nonce, ciphertext): (String, String, Vec<u8>) = conn
            .query_row(
                "SELECT key_id, nonce, ciphertext FROM records
             WHERE generation_id = ?1 AND record_id = ?2
             ORDER BY version_epoch DESC, version_counter DESC LIMIT 1",
                params![generation_id, record_id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .map_err(|_| VaultError::NotFound(record_id.to_string()))?;
        m02_cipher::decrypt_payload(&key_id, &nonce, &ciphertext)
    }

    fn view_f(
        conn: &Connection,
        record_id: &str,
        generation_hint: Option<i64>,
    ) -> Result<String, VaultError> {
        let gen = generation_hint.ok_or_else(|| VaultError::NotFound(record_id.to_string()))?;
        Self::read_for_generation(conn, gen, record_id)
    }

    pub fn logical_records_for_generation(
        conn: &Connection,
        generation_id: i64,
    ) -> Result<Vec<LogicalRecord>, VaultError> {
        let mut stmt = conn.prepare(
            "SELECT record_id, key_id, nonce, ciphertext, version_epoch, version_counter
             FROM records WHERE generation_id = ?1
             ORDER BY record_id, version_epoch, version_counter",
        )?;
        let rows = stmt.query_map([generation_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Vec<u8>>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, i64>(5)?,
            ))
        })?;
        let mut out = Vec::new();
        for row in rows {
            let (record_id, key_id, nonce, ciphertext, epoch, counter) = row?;
            let payload = m02_cipher::decrypt_payload(&key_id, &nonce, &ciphertext)?;
            out.push(LogicalRecord {
                record_id,
                payload,
                version: RecordVersion::new(epoch as u64, counter as u64),
            });
        }
        Ok(out)
    }
}
