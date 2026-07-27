use m01_seal::VaultConfig;
use m03::VaultStore;

use crate::output::{print_json, print_ok};

pub fn cmd_init(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    m03::VaultStore::init_database(db_path, config)?;
    if json {
        print_json(&serde_json::json!({"status": "initialized", "database": db_path}));
    } else {
        print_ok(&format!("initialized {db_path}"));
    }
    Ok(())
}

pub fn cmd_put(
    db_path: &str,
    config: &VaultConfig,
    record_id: &str,
    payload: &str,
    json: bool,
) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    store.put_record(record_id, payload)?;
    if json {
        print_json(&serde_json::json!({"record_id": record_id, "status": "stored"}));
    } else {
        print_ok(&format!("stored {record_id}"));
    }
    Ok(())
}

pub fn cmd_get(
    db_path: &str,
    config: &VaultConfig,
    record_id: &str,
    json: bool,
) -> Result<(), m01_seal::VaultError> {
    let store = VaultStore::open(db_path, config.clone())?;
    let payload = store.get_record(record_id)?;
    if json {
        print_json(&serde_json::json!({"record_id": record_id, "payload": payload}));
    } else {
        println!("{payload}");
    }
    Ok(())
}

pub fn cmd_reader_open(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    let snapshot = store.reader_open()?;
    if json {
        print_json(&serde_json::json!({
            "token": snapshot.token,
            "reader_id": snapshot.reader_id,
            "generation_id": snapshot.generation_id.0,
        }));
    } else {
        println!("{}", snapshot.token);
    }
    Ok(())
}

pub fn cmd_reader_get(
    db_path: &str,
    config: &VaultConfig,
    token: &str,
    record_id: &str,
    json: bool,
) -> Result<(), m01_seal::VaultError> {
    let store = VaultStore::open(db_path, config.clone())?;
    let payload = store.reader_get(token, record_id)?;
    if json {
        print_json(&serde_json::json!({"token": token, "record_id": record_id, "payload": payload}));
    } else {
        println!("{payload}");
    }
    Ok(())
}

pub fn cmd_reader_close(
    db_path: &str,
    config: &VaultConfig,
    token: &str,
    json: bool,
) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    store.reader_close(token)?;
    if json {
        print_json(&serde_json::json!({"token": token, "status": "closed"}));
    } else {
        print_ok(&format!("closed {token}"));
    }
    Ok(())
}

pub fn cmd_upgrade(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    store.upgrade()?;
    if json {
        print_json(&serde_json::json!({"status": "upgraded"}));
    } else {
        print_ok("upgrade complete");
    }
    Ok(())
}

pub fn cmd_recover(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    store.recover()?;
    if json {
        print_json(&serde_json::json!({"status": "recovered"}));
    } else {
        print_ok("recovery complete");
    }
    Ok(())
}

pub fn cmd_cleanup(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    store.cleanup()?;
    if json {
        print_json(&serde_json::json!({"status": "cleaned"}));
    } else {
        print_ok("cleanup complete");
    }
    Ok(())
}

pub fn cmd_status(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let store = VaultStore::open(db_path, config.clone())?;
    let status = store.status()?;
    if json {
        print_json(&status);
    } else {
        println!(
            "phase={:?} published={:?} readers={}",
            status.upgrade_phase, status.published_generation, status.active_reader_count
        );
    }
    Ok(())
}

pub fn cmd_inspect(db_path: &str, config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let store = VaultStore::open(db_path, config.clone())?;
    let report = store.inspect()?;
    if json {
        print_json(&report);
    } else {
        println!("generations={}", report.generations.len());
        println!("pins={}", report.pins.len());
        println!("reservations={}", report.nonce_reservation_count);
    }
    Ok(())
}

pub fn cmd_import_legacy(
    db_path: &str,
    config: &VaultConfig,
    source: &str,
    json: bool,
) -> Result<(), m01_seal::VaultError> {
    let mut store = VaultStore::open(db_path, config.clone())?;
    store.import_legacy(source)?;
    if json {
        print_json(&serde_json::json!({"status": "imported", "source": source, "database": db_path}));
    } else {
        print_ok(&format!("imported legacy from {source}"));
    }
    Ok(())
}

pub fn cmd_reset_demo(config: &VaultConfig, json: bool) -> Result<(), m01_seal::VaultError> {
    let fixture = "/app/fixtures/current-clean/store.db";
    let state_db = &config.database_path;
    if let Some(parent) = std::path::Path::new(state_db).parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::copy(fixture, state_db)?;
    let audit = &config.audit_path;
    if std::path::Path::new(audit).exists() {
        std::fs::remove_file(audit)?;
    }
    if json {
        print_json(&serde_json::json!({"status": "demo_reset", "database": state_db}));
    } else {
        print_ok("demo reset");
    }
    Ok(())
}
