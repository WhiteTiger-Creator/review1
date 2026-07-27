use rusqlite::{Connection, params};
use m01_seal::{RecordVersion, VaultConfig, VaultError};

use crate::schema::Schema;

pub struct LegacyAdapter;

impl LegacyAdapter {
    pub fn import_database(
        conn: &mut Connection,
        source_path: &str,
        config: &VaultConfig,
    ) -> Result<(), VaultError> {
        let legacy = rusqlite::Connection::open(source_path)?;
        let version: u32 = legacy
            .query_row(
                "SELECT value FROM metadata WHERE key = 'schema_version'",
                [],
                |row| row.get::<_, String>(0),
            )
            .unwrap_or_else(|_| "1".to_string())
            .parse()
            .unwrap_or(1);

        if !config.supported_legacy_versions.contains(&version) {
            return Err(VaultError::Incompatible(format!("legacy version {version} not supported")));
        }

        match version {
            1 => Self::import_v1(conn, &legacy, config),
            2 => Self::import_v2(conn, &legacy, config),
            _ => Err(VaultError::Incompatible(format!("unknown legacy version {version}"))),
        }
    }

    fn import_v1(conn: &mut Connection, legacy: &Connection, config: &VaultConfig) -> Result<(), VaultError> {
        Schema::create_current(conn)?;
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')",
            [],
        )?;
        conn.execute(
            "INSERT INTO generation_catalog (generation_id, state, key_id, schema_version, created_at)
             VALUES (1, 'published', ?1, 3, datetime('now'))",
            [&config.active_key_id],
        )?;

        let mut stmt = legacy.prepare(
            "SELECT record_id, key_id, nonce, ciphertext, version_epoch, version_counter FROM legacy_records",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Vec<u8>>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, i64>(5)?,
            ))
        })?;

        for row in rows {
            let (record_id, key_id, nonce, ciphertext, epoch, counter) = row?;
            if Self::norm_g(conn, &record_id, counter)? {
                continue;
            }
            conn.execute(
                "INSERT INTO records (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                 VALUES (?1, 1, ?2, ?3, ?4, ?5, ?6)",
                params![record_id, key_id, nonce, ciphertext, epoch, counter],
            )?;
        }
        Ok(())
    }

    fn import_v2(conn: &mut Connection, legacy: &Connection, config: &VaultConfig) -> Result<(), VaultError> {
        Schema::create_current(conn)?;
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')",
            [],
        )?;
        conn.execute(
            "INSERT INTO generation_catalog (generation_id, state, key_id, schema_version, created_at)
             VALUES (1, 'published', ?1, 3, datetime('now'))",
            [&config.active_key_id],
        )?;

        let mut stmt = legacy.prepare(
            "SELECT record_id, key_id, nonce, ciphertext, version_epoch, version_counter FROM records",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Vec<u8>>(3)?,
                row.get::<_, i64>(4)?,
                row.get::<_, i64>(5)?,
            ))
        })?;

        for row in rows {
            let (record_id, key_id, nonce, ciphertext, epoch, counter) = row?;
            let existing: Option<i64> = conn
                .query_row(
                    "SELECT version_counter FROM records WHERE record_id = ?1 AND generation_id = 1
                     ORDER BY version_counter DESC LIMIT 1",
                    [&record_id],
                    |row| row.get(0),
                )
                .ok();
            if existing.map_or(false, |c| c >= counter) {
                continue;
            }
            conn.execute(
                "INSERT INTO records (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
                 VALUES (?1, 1, ?2, ?3, ?4, ?5, ?6)",
                params![record_id, key_id, nonce, ciphertext, epoch, counter],
            )?;
        }
        Ok(())
    }

    fn norm_g(conn: &Connection, record_id: &str, counter: i64) -> Result<bool, VaultError> {
        let existing: Option<i64> = conn
            .query_row(
                "SELECT MAX(version_counter) FROM records WHERE record_id = ?1 AND generation_id = 1",
                [record_id],
                |row| row.get(0),
            )
            .ok();
        Ok(existing.map_or(false, |c| c >= counter))
    }

    pub fn compare_versions(a: &RecordVersion, b: &RecordVersion) -> std::cmp::Ordering {
        a.canonical_key().cmp(&b.canonical_key())
    }
}
