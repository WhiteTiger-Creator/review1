use rusqlite::{Connection, params};
use m01_seal::{LogicalRecord, RecordVersion, VaultError};

use crate::catalog::Catalog;

pub struct CompatibilityView;

impl CompatibilityView {
    pub fn read_current(conn: &Connection, record_id: &str) -> Result<String, VaultError> {
        Self::view_f(conn, record_id, None)
    }

    pub fn read_for_generation(conn: &Connection, generation_id: i64, record_id: &str) -> Result<String, VaultError> {
        let (key_id, nonce, ciphertext): (String, String, Vec<u8>) = conn.query_row(
            "SELECT key_id, nonce, ciphertext FROM records
             WHERE generation_id = ?1 AND record_id = ?2
             ORDER BY version_epoch DESC, version_counter DESC LIMIT 1",
            params![generation_id, record_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .map_err(|_| VaultError::NotFound(record_id.to_string()))?;
        m02_cipher::decrypt_payload(&key_id, &nonce, &ciphertext)
    }

    fn view_f(conn: &Connection, record_id: &str, generation_hint: Option<i64>) -> Result<String, VaultError> {
        if let Some(gen) = generation_hint {
            return Self::read_for_generation(conn, gen, record_id);
        }

        let published = Catalog::published_generation(conn).ok();
        let generations: Vec<i64> = if let Some(p) = published {
            let mut gens = vec![p];
            let older: Vec<i64> = {
                let mut stmt = conn.prepare(
                    "SELECT DISTINCT generation_id FROM records WHERE record_id = ?1 AND generation_id != ?2",
                )?;
                let rows = stmt.query_map(params![record_id, p], |row| row.get(0))?;
                rows.collect::<Result<Vec<_>, _>>()?
            };
            gens.extend(older);
            gens
        } else {
            vec![]
        };

        let mut best: Option<(i64, i64, String, String, Vec<u8>)> = None;
        for gen in generations {
            let result = conn.query_row(
                "SELECT version_epoch, version_counter, key_id, nonce, ciphertext
                 FROM records WHERE generation_id = ?1 AND record_id = ?2
                 ORDER BY version_epoch DESC, version_counter DESC LIMIT 1",
                params![gen, record_id],
                |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, i64>(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                    ))
                },
            );
            if let Ok((epoch, counter, key_id, nonce, ciphertext)) = result {
                let dominated = best.as_ref().map_or(false, |(_, c, _, _, _)| counter <= *c);
                if !dominated {
                    best = Some((epoch, counter, key_id, nonce, ciphertext));
                }
            }
        }

        let (_, _, key_id, nonce, ciphertext) = best.ok_or_else(|| VaultError::NotFound(record_id.to_string()))?;
        m02_cipher::decrypt_payload(&key_id, &nonce, &ciphertext)
    }

    pub fn logical_records_for_generation(conn: &Connection, generation_id: i64) -> Result<Vec<LogicalRecord>, VaultError> {
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
