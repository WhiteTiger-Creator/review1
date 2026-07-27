use rusqlite::Connection;
use m01_seal::VaultError;

pub struct Schema;

impl Schema {
    pub fn create_current(conn: &Connection) -> Result<(), VaultError> {
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT NOT NULL,
                generation_id INTEGER NOT NULL,
                key_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                version_epoch INTEGER NOT NULL DEFAULT 0,
                version_counter INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (record_id, generation_id, version_epoch, version_counter)
            );
            CREATE INDEX IF NOT EXISTS idx_records_gen ON records(generation_id);

            CREATE TABLE IF NOT EXISTS generation_catalog (
                generation_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                key_id TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS upgrade_journal (
                upgrade_id TEXT PRIMARY KEY,
                phase TEXT NOT NULL,
                source_generation_id INTEGER NOT NULL,
                target_generation_id INTEGER NOT NULL,
                copy_cursor INTEGER NOT NULL DEFAULT 0,
                reservation_batch INTEGER NOT NULL DEFAULT 0,
                last_action TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reader_pins (
                token TEXT PRIMARY KEY,
                reader_id TEXT NOT NULL,
                generation_id INTEGER NOT NULL,
                lease_epoch INTEGER NOT NULL,
                opened_seq INTEGER NOT NULL,
                released INTEGER NOT NULL DEFAULT 0,
                session_id TEXT
            );

            CREATE TABLE IF NOT EXISTS nonce_reservations (
                upgrade_id TEXT NOT NULL,
                batch_number INTEGER NOT NULL,
                slot INTEGER NOT NULL,
                key_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                record_id TEXT,
                consumed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (upgrade_id, batch_number, slot)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                operation TEXT NOT NULL,
                upgrade_id TEXT,
                phase TEXT,
                outcome TEXT NOT NULL,
                source_generation INTEGER,
                target_generation INTEGER,
                reader_count INTEGER,
                reason_code TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE VIEW IF NOT EXISTS compatibility_view AS
            SELECT r.*
            FROM records r
            INNER JOIN (
                SELECT record_id, generation_id, MAX(version_counter) AS max_counter
                FROM records
                GROUP BY record_id, generation_id
            ) latest ON r.record_id = latest.record_id
                AND r.generation_id = latest.generation_id
                AND r.version_counter = latest.max_counter;
            ",
        )?;
        Ok(())
    }

    pub fn schema_version(conn: &Connection) -> Result<u32, VaultError> {
        let version: String = conn
            .query_row(
                "SELECT value FROM metadata WHERE key = 'schema_version'",
                [],
                |row| row.get(0),
            )
            .unwrap_or_else(|_| "3".to_string());
        version.parse().map_err(|_| VaultError::Incompatible("invalid schema version".into()))
    }
}
