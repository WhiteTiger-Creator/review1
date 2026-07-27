use rusqlite::Connection;
use m01_seal::{VaultConfig, VaultError};

use crate::catalog::Catalog;
use crate::copy::CopyPlanner;
use crate::journal::Journal;
use crate::pins::PinManager;
use crate::publish::Publisher;
use crate::schema::Schema;

pub struct RecoveryPlanner;

impl RecoveryPlanner {
    pub fn run(conn: &mut Connection, config: &VaultConfig, session_id: &str) -> Result<(), VaultError> {
        let journal = Journal::read_for_recover(conn)?;
        let Some((upgrade_id, phase, source, target, _cursor, _batch)) = journal else {
            return Ok(());
        };

        Self::phase_b(conn, &upgrade_id, phase, source, target, config, session_id)
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
        Journal::set_phase(conn, upgrade_id, m01_seal::UpgradePhase::Copying)?;

        let schema_version = Schema::schema_version(conn)?;
        if schema_version > 3 {
            return Err(VaultError::Incompatible(format!("unsupported schema {schema_version}")));
        }

        match phase {
            m01_seal::UpgradePhase::Reserved | m01_seal::UpgradePhase::Copying => {
                CopyPlanner::resume_copy(conn, upgrade_id, source, target, config)?;
                Publisher::publish(conn, upgrade_id, target)?;
                Publisher::validate_target(conn, upgrade_id, target)?;
            }
            m01_seal::UpgradePhase::Copied | m01_seal::UpgradePhase::Validated => {
                Publisher::publish(conn, upgrade_id, target)?;
                Publisher::validate_target(conn, upgrade_id, target)?;
            }
            m01_seal::UpgradePhase::Published => {
                PinManager::reconcile_pins(conn, session_id, target)?;
                Catalog::mark_cleanup_pending(conn, target)?;
                Journal::complete(conn, upgrade_id)?;
                return Ok(());
            }
            m01_seal::UpgradePhase::PinsReconciled | m01_seal::UpgradePhase::CleanupPending => {
                Catalog::mark_cleanup_pending(conn, target)?;
                Journal::complete(conn, upgrade_id)?;
                return Ok(());
            }
            m01_seal::UpgradePhase::Complete => return Ok(()),
            _ => {}
        }

        if matches!(
            phase,
            m01_seal::UpgradePhase::Reserved
                | m01_seal::UpgradePhase::Copying
                | m01_seal::UpgradePhase::Copied
                | m01_seal::UpgradePhase::Validated
        ) {
            PinManager::reconcile_pins(conn, session_id, target)?;
            Catalog::mark_cleanup_pending(conn, target)?;
            Journal::complete(conn, upgrade_id)?;
        }
        Ok(())
    }
}
