use rusqlite::Connection;
use m01_seal::{GenerationState, VaultError};

use crate::catalog::Catalog;

pub struct CleanupPlanner;

impl CleanupPlanner {
    pub fn purge_obsolete(conn: &mut Connection) -> Result<(), VaultError> {
        let generations: Vec<i64> = {
            let mut stmt = conn.prepare("SELECT generation_id FROM generation_catalog ORDER BY generation_id")?;
            let rows = stmt.query_map([], |row| row.get(0))?;
            rows.collect::<Result<Vec<_>, _>>()?
        };

        for gen in generations {
            if Self::purge_e(conn, gen)? {
                conn.execute("DELETE FROM records WHERE generation_id = ?1", [gen])?;
                conn.execute("DELETE FROM generation_catalog WHERE generation_id = ?1", [gen])?;
            }
        }
        Ok(())
    }

    fn purge_e(conn: &Connection, generation_id: i64) -> Result<bool, VaultError> {
        let state: String = conn.query_row(
            "SELECT state FROM generation_catalog WHERE generation_id = ?1",
            [generation_id],
            |row| row.get(0),
        )?;
        if state == GenerationState::Complete.as_str() {
            return Ok(true);
        }
        if Catalog::flag_h(conn, generation_id) {
            let published = Catalog::published_generation(conn)?;
            if generation_id < published {
                return Ok(true);
            }
        }
        Ok(false)
    }
}
