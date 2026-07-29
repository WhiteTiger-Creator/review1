pub mod catalog;
pub mod cleanup;
pub mod compatibility;
pub mod connection;
pub mod copy;
pub mod journal;
pub mod legacy;
pub mod pins;
pub mod publish;
pub mod recover;
pub mod schema;

use rusqlite::Connection;
use m01_seal::{
    check_failpoint, AuditEntry, InspectReport, LogicalRecord, ReaderSnapshot, StatusReport,
    UpgradePhase, VaultConfig, VaultError,
};

use crate::catalog::Catalog;
use crate::cleanup::CleanupPlanner;
use crate::compatibility::CompatibilityView;
use crate::connection::open_connection;
use crate::copy::CopyPlanner;
use crate::journal::Journal;
use crate::legacy::LegacyAdapter;
use crate::pins::PinManager;
use crate::publish::Publisher;
use crate::recover::RecoveryPlanner;
use crate::schema::Schema;

pub struct VaultStore {
    conn: Connection,
    config: VaultConfig,
    session_id: String,
    audit_path: String,
}

impl VaultStore {
    pub fn open(database_path: &str, config: VaultConfig) -> Result<Self, VaultError> {
        let audit_path = config.audit_path.clone();
        let conn = open_connection(database_path)?;
        let session_id = uuid::Uuid::new_v4().to_string();
        Ok(Self {
            conn,
            config,
            session_id,
            audit_path,
        })
    }

    pub fn init_database(database_path: &str, config: &VaultConfig) -> Result<(), VaultError> {
        if let Some(parent) = std::path::Path::new(database_path).parent() {
            std::fs::create_dir_all(parent)?;
        }
        let conn = open_connection(database_path)?;
        Schema::create_current(&conn)?;
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '3')",
            [],
        )?;
        let key_id = &config.active_key_id;
        conn.execute(
            "INSERT INTO generation_catalog (generation_id, state, key_id, schema_version, created_at)
             VALUES (1, 'published', ?1, 3, datetime('now'))",
            [key_id],
        )?;
        Ok(())
    }

    pub fn put_record(&mut self, record_id: &str, payload: &str) -> Result<(), VaultError> {
        let gen = Catalog::current_generation(&self.conn)?;
        let version = Catalog::next_record_version(&self.conn, record_id, gen)?;
        let nonce = m02_cipher::allocate_nonce(&self.config.active_key_id, gen, 0, version.counter as i64);
        let ciphertext = m02_cipher::encrypt_payload(&self.config.active_key_id, &nonce, payload)?;
        self.conn.execute(
            "INSERT INTO records (record_id, generation_id, key_id, nonce, ciphertext, version_epoch, version_counter)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            rusqlite::params![
                record_id,
                gen,
                self.config.active_key_id,
                nonce,
                ciphertext,
                version.epoch,
                version.counter
            ],
        )?;
        self.append_audit(AuditEntry {
            timestamp: chrono_now(),
            operation: "put".into(),
            upgrade_id: None,
            phase: None,
            outcome: "ok".into(),
            source_generation: None,
            target_generation: Some(gen),
            reader_count: None,
            reason_code: "record_written".into(),
        })?;
        Ok(())
    }

    pub fn get_record(&self, record_id: &str) -> Result<String, VaultError> {
        CompatibilityView::read_current(&self.conn, record_id)
    }

    pub fn reader_open(&mut self) -> Result<ReaderSnapshot, VaultError> {
        PinManager::open_reader(&mut self.conn, &self.session_id)
    }

    pub fn reader_get(&self, token: &str, record_id: &str) -> Result<String, VaultError> {
        let gen = PinManager::generation_for_token(&self.conn, token)?;
        CompatibilityView::read_for_generation(&self.conn, gen, record_id)
    }

    pub fn reader_close(&mut self, token: &str) -> Result<(), VaultError> {
        PinManager::close_reader(&mut self.conn, token)
    }

    pub fn upgrade(&mut self) -> Result<(), VaultError> {
        if Journal::active_upgrade(&self.conn)?.is_some() {
            return Err(VaultError::InvalidState("upgrade already in progress".into()));
        }
        let source = Catalog::published_generation(&self.conn)?;
        let target = Catalog::create_target_generation(&mut self.conn, &self.config.active_key_id)?;
        let upgrade_id = uuid::Uuid::new_v4().to_string();
        Journal::begin(&mut self.conn, &upgrade_id, source, target)?;

        CopyPlanner::reserve_batch(&mut self.conn, &upgrade_id, target, &self.config)?;
        check_failpoint("after-reservation").map_err(|c| VaultError::InvalidState(format!("failpoint:{c}")))?;

        CopyPlanner::copy_batches(&mut self.conn, &upgrade_id, source, target, &self.config)?;
        check_failpoint("after-copy-complete").map_err(|c| VaultError::InvalidState(format!("failpoint:{c}")))?;

        Publisher::publish(&mut self.conn, &upgrade_id, target)?;
        check_failpoint("after-publication").map_err(|c| VaultError::InvalidState(format!("failpoint:{c}")))?;

        Publisher::validate_target(&self.conn, &upgrade_id, target)?;
        check_failpoint("after-target-validation").map_err(|c| VaultError::InvalidState(format!("failpoint:{c}")))?;

        PinManager::reconcile_pins(&mut self.conn, &self.session_id, target)?;
        check_failpoint("after-pin-reconciliation").map_err(|c| VaultError::InvalidState(format!("failpoint:{c}")))?;

        Catalog::mark_cleanup_pending(&mut self.conn, target)?;
        Journal::complete(&mut self.conn, &upgrade_id)?;

        self.append_audit(AuditEntry {
            timestamp: chrono_now(),
            operation: "upgrade".into(),
            upgrade_id: Some(upgrade_id),
            phase: Some(UpgradePhase::Complete.as_str().into()),
            outcome: "ok".into(),
            source_generation: Some(source),
            target_generation: Some(target),
            reader_count: Some(PinManager::active_count(&self.conn)?),
            reason_code: "upgrade_complete".into(),
        })?;
        Ok(())
    }

    pub fn recover(&mut self) -> Result<(), VaultError> {
        RecoveryPlanner::run(&mut self.conn, &self.config, &self.session_id)?;
        self.append_audit(AuditEntry {
            timestamp: chrono_now(),
            operation: "recover".into(),
            upgrade_id: Journal::active_upgrade(&self.conn)?.map(|(id, _)| id),
            phase: Journal::active_upgrade(&self.conn)?.map(|(_, p)| p.as_str().to_string()),
            outcome: "ok".into(),
            source_generation: None,
            target_generation: Catalog::published_generation(&self.conn).ok(),
            reader_count: Some(PinManager::active_count(&self.conn)?),
            reason_code: "recovery_applied".into(),
        })?;
        Ok(())
    }

    pub fn cleanup(&mut self) -> Result<(), VaultError> {
        check_failpoint("during-cleanup").map_err(|c| VaultError::InvalidState(format!("failpoint:{c}")))?;
        CleanupPlanner::purge_obsolete(&mut self.conn)?;
        self.append_audit(AuditEntry {
            timestamp: chrono_now(),
            operation: "cleanup".into(),
            upgrade_id: None,
            phase: Some(UpgradePhase::CleanupPending.as_str().into()),
            outcome: "ok".into(),
            source_generation: None,
            target_generation: Catalog::published_generation(&self.conn).ok(),
            reader_count: Some(PinManager::active_count(&self.conn)?),
            reason_code: "cleanup_complete".into(),
        })?;
        Ok(())
    }

    pub fn status(&self) -> Result<StatusReport, VaultError> {
        Catalog::status_report(&self.conn, &self.config.database_path)
    }

    pub fn inspect(&self) -> Result<InspectReport, VaultError> {
        Catalog::inspect_report(&self.conn)
    }

    pub fn import_legacy(&mut self, source_path: &str) -> Result<(), VaultError> {
        LegacyAdapter::import_database(&mut self.conn, source_path, &self.config)
    }

    pub fn logical_records(&self, generation_id: i64) -> Result<Vec<LogicalRecord>, VaultError> {
        CompatibilityView::logical_records_for_generation(&self.conn, generation_id)
    }

    fn append_audit(&self, entry: AuditEntry) -> Result<(), VaultError> {
        if let Some(parent) = std::path::Path::new(&self.audit_path).parent() {
            std::fs::create_dir_all(parent)?;
        }
        use std::io::Write;
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.audit_path)?;
        let line = serde_json::to_string(&entry)?;
        writeln!(file, "{line}")?;
        Ok(())
    }
}

fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{secs}")
}
