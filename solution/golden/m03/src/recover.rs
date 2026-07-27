use m01_seal::{VaultConfig, VaultError};
use rusqlite::Connection;

use crate::catalog::Catalog;
use crate::copy::CopyPlanner;
use crate::journal::Journal;
use crate::pins::PinManager;
use crate::publish::Publisher;
use crate::schema::Schema;

pub struct RecoveryPlanner;

impl RecoveryPlanner {
    pub fn run(
        conn: &mut Connection,
        config: &VaultConfig,
        session_id: &str,
    ) -> Result<(), VaultError> {
        let journal = Journal::read_for_recover(conn)?;
        let Some((upgrade_id, phase, source, target, _cursor, _batch)) = journal else {
            return Ok(());
        };

        Self::validate_before_mutate(conn, &upgrade_id, source, target)?;

        Self::phase_b(conn, &upgrade_id, phase, source, target, config, session_id)
    }

    fn validate_before_mutate(
        conn: &Connection,
        upgrade_id: &str,
        source: i64,
        target: i64,
    ) -> Result<(), VaultError> {
        let schema_version = Schema::schema_version(conn)?;
        if schema_version > 3 {
            return Err(VaultError::Incompatible(format!(
                "unsupported schema {schema_version}"
            )));
        }
        let exists: i64 = conn.query_row(
            "SELECT COUNT(*) FROM upgrade_journal WHERE upgrade_id = ?1",
            [upgrade_id],
            |row| row.get(0),
        )?;
        if exists == 0 {
            return Err(VaultError::InvalidState("missing upgrade journal".into()));
        }
        for gen in [source, target] {
            let count: i64 = conn.query_row(
                "SELECT COUNT(*) FROM generation_catalog WHERE generation_id = ?1",
                [gen],
                |row| row.get(0),
            )?;
            if count == 0 {
                return Err(VaultError::InvalidState(format!(
                    "missing generation {gen}"
                )));
            }
        }
        Ok(())
    }

    fn phase_b(
        conn: &mut Connection,
        upgrade_id: &str,
        phase: m01_seal::UpgradePhase,
        source: i64,
        target: i64,
        config: &VaultConfig,
        session_id: &str,
    ) -> Result<(), VaultError> {
        match phase {
            m01_seal::UpgradePhase::Reserved | m01_seal::UpgradePhase::Copying => {
                CopyPlanner::resume_copy(conn, upgrade_id, source, target, config)?;
                Publisher::validate_target(conn, upgrade_id, target)?;
                Publisher::publish(conn, upgrade_id, target)?;
                PinManager::reconcile_pins(conn, session_id, target)?;
                Catalog::mark_cleanup_pending(conn, target)?;
                Catalog::set_state(conn, source, m01_seal::GenerationState::Complete)?;
                Catalog::set_state(conn, target, m01_seal::GenerationState::Complete)?;
                Journal::complete(conn, upgrade_id)?;
            }
            m01_seal::UpgradePhase::Copied | m01_seal::UpgradePhase::Validated => {
                Publisher::publish(conn, upgrade_id, target)?;
                PinManager::reconcile_pins(conn, session_id, target)?;
                Catalog::mark_cleanup_pending(conn, target)?;
                Catalog::set_state(conn, source, m01_seal::GenerationState::Complete)?;
                Catalog::set_state(conn, target, m01_seal::GenerationState::Complete)?;
                Journal::complete(conn, upgrade_id)?;
            }
            m01_seal::UpgradePhase::Published => {
                PinManager::reconcile_pins(conn, session_id, target)?;
                Catalog::mark_cleanup_pending(conn, target)?;
                Catalog::set_state(conn, source, m01_seal::GenerationState::Complete)?;
                Catalog::set_state(conn, target, m01_seal::GenerationState::Complete)?;
                Journal::complete(conn, upgrade_id)?;
            }
            m01_seal::UpgradePhase::PinsReconciled | m01_seal::UpgradePhase::CleanupPending => {
                Catalog::set_state(conn, source, m01_seal::GenerationState::Complete)?;
                Catalog::set_state(conn, target, m01_seal::GenerationState::Complete)?;
                Journal::complete(conn, upgrade_id)?;
            }
            m01_seal::UpgradePhase::Complete => {}
            _ => {}
        }
        Ok(())
    }
}
