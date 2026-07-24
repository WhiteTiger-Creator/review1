use anyhow::{Context, Result};
use rusqlite::Connection;
use std::path::Path;

pub fn apply_migrations(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY
        );",
    )?;
    let migrations_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../migrations");
    let mut versions: Vec<_> = std::fs::read_dir(&migrations_dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().is_some_and(|x| x == "sql"))
        .map(|e| e.path())
        .collect();
    versions.sort();
    for path in versions {
        let name = path.file_name().unwrap().to_string_lossy();
        let version: i64 = name
            .split('_')
            .next()
            .unwrap()
            .parse()
            .context("migration version")?;
        let applied: bool = conn
            .query_row(
                "SELECT 1 FROM schema_migrations WHERE version = ?1",
                [version],
                |_| Ok(()),
            )
            .is_ok();
        if applied {
            continue;
        }
        let sql = std::fs::read_to_string(&path)?;
        conn.execute_batch(&sql)?;
        conn.execute(
            "INSERT INTO schema_migrations(version) VALUES(?1)",
            [version],
        )?;
    }
    Ok(())
}
