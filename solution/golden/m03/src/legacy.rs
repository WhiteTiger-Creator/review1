use std::collections::HashMap;

use m01_seal::{RecordVersion, VaultConfig, VaultError};
use rusqlite::{params, Connection};

use crate::schema::Schema;

pub struct LegacyAdapter;

struct LegacyRow {
    record_id: String,
    key_id: String,
    nonce: String,
    ciphertext: Vec<u8>,
    epoch: i64,
    counter: i64,
}

impl LegacyAdapter {
    pub fn import_database(
        conn: &mut Connection,
        source_path: &str,
        config: &VaultConfig,
    ) -> Result<(), VaultError> {
        let legacy = Connection::open(source_path)
            .map_err(|e| VaultError::Incompatible(format!("cannot open legacy source: {e}")))?;
        let version = Self::read_source_version(&legacy)?;
        if !config.supported_legacy_versions.contains(&version) {
            return Err(VaultError::Incompatible(format!(
                "legacy version {version} not supported"
            )));
        }

        let rows = match version {
            1 => Self::load_v1(&legacy)?,
            2 => Self::load_v2(&legacy)?,
            _ => {
                return Err(VaultError::Incompatible(format!(
                    "unknown legacy version {version}"
                )))
            }
        };
        let newest = Self::select_newest(rows);

        Self::ensure_target_accepts_import(conn)?;

        let tx = conn.transaction()?;
        Schema::create_current(&tx)?;
        tx.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')",
            [],
        )?;
        let gen_exists: i64 = tx.query_row(
            "SELECT COUNT(*) FROM generation_catalog WHERE generation_id = 1",
            [],
            |row| row.get(0),
        )?;
        if gen_exists == 0 {
            tx.execute(
                "INSERT INTO generation_catalog (generation_id, state, key_id, schema_version, created_at)
                 VALUES (1, 'published', ?1, 3, datetime('now'))",
                [&config.active_key_id],
            )?;
        } else {
            tx.execute(
                "UPDATE generation_catalog SET state = 'published', key_id = ?1, schema_version = 3
                 WHERE generation_id = 1",
                [&config.active_key_id],
            )?;
        }

        for row in newest.values() {
            tx.execute(
                "DELETE FROM records WHERE record_id = ?1 AND generation_id = 1",
                [&row.record_id],
            )?;
            tx.execute(
                "INSERT INTO records (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                 VALUES (?1, 1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    row.record_id,
                    row.key_id,
                    row.nonce,
                    row.ciphertext,
                    row.epoch,
                    row.counter
                ],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    fn read_source_version(legacy: &Connection) -> Result<u32, VaultError> {
        let has_meta: i64 = legacy
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'metadata'",
                [],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if has_meta == 0 {
            return Err(VaultError::Incompatible(
                "malformed legacy source: missing metadata".into(),
            ));
        }
        let version: u32 = legacy
            .query_row(
                "SELECT value FROM metadata WHERE key = 'schema_version'",
                [],
                |row| row.get::<_, String>(0),
            )
            .map_err(|_| {
                VaultError::Incompatible("malformed legacy source: missing schema_version".into())
            })?
            .parse()
            .map_err(|_| VaultError::Incompatible("invalid legacy schema_version".into()))?;
        Ok(version)
    }

    fn table_exists(conn: &Connection, name: &str) -> Result<bool, VaultError> {
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?1",
            [name],
            |row| row.get(0),
        )?;
        Ok(count > 0)
    }

    fn load_v1(legacy: &Connection) -> Result<Vec<LegacyRow>, VaultError> {
        if !Self::table_exists(legacy, "legacy_records")? {
            return Err(VaultError::Incompatible(
                "malformed legacy v1 source: missing legacy_records".into(),
            ));
        }
        let mut stmt = legacy.prepare(
            "SELECT record_id, key_id, nonce, ciphertext, version_epoch, version_counter
             FROM legacy_records",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(LegacyRow {
                record_id: row.get(0)?,
                key_id: row.get(1)?,
                nonce: row.get(2)?,
                ciphertext: row.get(3)?,
                epoch: row.get(4)?,
                counter: row.get(5)?,
            })
        })?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    fn load_v2(legacy: &Connection) -> Result<Vec<LegacyRow>, VaultError> {
        if !Self::table_exists(legacy, "records")? {
            return Err(VaultError::Incompatible(
                "malformed legacy v2 source: missing records".into(),
            ));
        }
        let mut stmt = legacy.prepare(
            "SELECT record_id, key_id, nonce, ciphertext, version_epoch, version_counter
             FROM records",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(LegacyRow {
                record_id: row.get(0)?,
                key_id: row.get(1)?,
                nonce: row.get(2)?,
                ciphertext: row.get(3)?,
                epoch: row.get(4)?,
                counter: row.get(5)?,
            })
        })?;
        let mut out = Vec::new();
        for row in rows {
            out.push(row?);
        }
        Ok(out)
    }

    fn select_newest(rows: Vec<LegacyRow>) -> HashMap<String, LegacyRow> {
        let mut best: HashMap<String, LegacyRow> = HashMap::new();
        for row in rows {
            match best.get(&row.record_id) {
                Some(cur) if (row.epoch, row.counter) <= (cur.epoch, cur.counter) => {}
                _ => {
                    best.insert(row.record_id.clone(), row);
                }
            }
        }
        best
    }

    fn ensure_target_accepts_import(conn: &Connection) -> Result<(), VaultError> {
        let has_records_table: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'records'",
                [],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if has_records_table == 0 {
            return Ok(());
        }

        let record_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM records", [], |row| row.get(0))
            .unwrap_or(0);
        let active_upgrade: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM upgrade_journal WHERE phase NOT IN ('complete', 'idle')",
                [],
                |row| row.get(0),
            )
            .unwrap_or(0);

        if active_upgrade > 0 {
            return Err(VaultError::InvalidState(
                "cannot import while an upgrade is active".into(),
            ));
        }
        if record_count > 0 {
            return Err(VaultError::InvalidState(
                "refusing import into non-empty target".into(),
            ));
        }
        Ok(())
    }

    pub fn compare_versions(a: &RecordVersion, b: &RecordVersion) -> std::cmp::Ordering {
        a.canonical_key().cmp(&b.canonical_key())
    }
}
