mod commands;
mod output;

use clap::{Parser, Subcommand};
use m01_seal::VaultConfig;

#[derive(Parser)]
#[command(name = "opsctl", about = "Credential store operator CLI")]
struct Cli {
    #[arg(long, global = true)]
    db: Option<String>,

    #[arg(long, global = true)]
    json: bool,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Init,
    Put {
        record_id: String,
        payload: String,
    },
    Get {
        record_id: String,
    },
    ReaderOpen,
    ReaderGet {
        token: String,
        record_id: String,
    },
    ReaderClose {
        token: String,
    },
    Upgrade,
    Recover,
    Cleanup,
    Status,
    Inspect,
    ResetDemo,
    ImportLegacy {
        #[arg(long)]
        source: String,
    },
}

fn main() {
    let cli = Cli::parse();
    let config = load_config();
    let db_path = cli.db.unwrap_or(config.database_path.clone());

    let result = match cli.command {
        Commands::Init => commands::cmd_init(&db_path, &config, cli.json),
        Commands::Put { record_id, payload } => {
            commands::cmd_put(&db_path, &config, &record_id, &payload, cli.json)
        }
        Commands::Get { record_id } => commands::cmd_get(&db_path, &config, &record_id, cli.json),
        Commands::ReaderOpen => commands::cmd_reader_open(&db_path, &config, cli.json),
        Commands::ReaderGet { token, record_id } => {
            commands::cmd_reader_get(&db_path, &config, &token, &record_id, cli.json)
        }
        Commands::ReaderClose { token } => {
            commands::cmd_reader_close(&db_path, &config, &token, cli.json)
        }
        Commands::Upgrade => commands::cmd_upgrade(&db_path, &config, cli.json),
        Commands::Recover => commands::cmd_recover(&db_path, &config, cli.json),
        Commands::Cleanup => commands::cmd_cleanup(&db_path, &config, cli.json),
        Commands::Status => commands::cmd_status(&db_path, &config, cli.json),
        Commands::Inspect => commands::cmd_inspect(&db_path, &config, cli.json),
        Commands::ResetDemo => commands::cmd_reset_demo(&config, cli.json),
        Commands::ImportLegacy { source } => {
            commands::cmd_import_legacy(&db_path, &config, &source, cli.json)
        }
    };

    if let Err(e) = result {
        if cli.json {
            eprintln!("{}", serde_json::json!({"error": e.to_string(), "code": "error"}));
        } else {
            eprintln!("error: {e}");
        }
        let msg = e.to_string();
        if msg.contains("failpoint:") {
            if let Some(code) = msg.split("failpoint:").nth(1) {
                if let Ok(c) = code.parse::<i32>() {
                    std::process::exit(c);
                }
            }
            std::process::exit(m01_seal::FAILPOINT_EXIT_CODE);
        }
        std::process::exit(1);
    }
}

fn load_config() -> VaultConfig {
    let path = std::env::var("KSEAL_CONFIG").unwrap_or_else(|_| "/app/config/service.toml".into());
    if let Ok(contents) = std::fs::read_to_string(&path) {
        parse_toml_config(&contents).unwrap_or_default()
    } else {
        VaultConfig::default()
    }
}

fn parse_toml_config(contents: &str) -> Result<VaultConfig, String> {
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
                "supported_legacy_versions" => {
                    let inner = value.trim_matches(|c| c == '[' || c == ']');
                    config.supported_legacy_versions = inner
                        .split(',')
                        .filter_map(|v| v.trim().parse().ok())
                        .collect();
                }
                _ => {}
            }
        }
    }
    Ok(config)
}
