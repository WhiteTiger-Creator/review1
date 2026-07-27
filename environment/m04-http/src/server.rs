use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use axum::Router;
use m01_seal::VaultConfig;
use m03::VaultStore;

use crate::routes::build_router;

pub struct AppState {
    pub config: VaultConfig,
    pub store: Mutex<VaultStore>,
}

pub fn load_config(path: &str) -> VaultConfig {
    if let Ok(contents) = std::fs::read_to_string(path) {
        parse_toml(&contents).unwrap_or_default()
    } else {
        VaultConfig::default()
    }
}

fn parse_toml(contents: &str) -> Result<VaultConfig, String> {
    let mut config = VaultConfig::default();
    for line in contents.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((key, value)) = line.split_once('=') {
            let key = key.trim();
            let value = value.trim().trim_matches('"');
            match key {
                "database_path" => config.database_path = value.to_string(),
                "audit_path" => config.audit_path = value.to_string(),
                "batch_size" => config.batch_size = value.parse().unwrap_or(3),
                "active_key_id" => config.active_key_id = value.to_string(),
                _ => {}
            }
        }
    }
    Ok(config)
}

pub async fn run(listen: &str, config: VaultConfig) {
    let db_path = config.database_path.clone();
    let store = VaultStore::open(&db_path, config.clone()).expect("open database");
    let state = Arc::new(AppState {
        config,
        store: Mutex::new(store),
    });
    let app: Router = build_router(state);
    let addr: SocketAddr = listen.parse().expect("valid listen address");
    println!("opsd listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.expect("bind");
    axum::serve(listener, app).await.expect("serve");
}
