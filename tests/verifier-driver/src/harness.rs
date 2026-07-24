use crate::cases::ALL_CASES;
use anyhow::{bail, Context, Result};
use std::path::Path;
use std::process::Command;
use std::sync::Once;

const CANDIDATE_UID: &str = "10001";
const CANDIDATE_GID: &str = "10001";
const SETPRIV: &str = "/usr/bin/setpriv";
const CARGO: &str = "/usr/local/cargo/bin/cargo";
const CLI: &str = "/app/target/release/rstore-cli";
const AGENT_HOME: &str = "/home/agent";
const AGENT_CARGO_HOME: &str = "/home/agent/.cargo";
const VENDOR_DIR: &str = "/opt/cargo/vendor";

static BUILD_ONCE: Once = Once::new();

pub struct TestCase {
    pub name: &'static str,
    pub check: fn() -> Result<()>,
}

pub fn run_all() -> Result<()> {
    BUILD_ONCE.call_once(|| {
        if let Err(err) = build_candidate() {
            eprintln!("candidate build failed: {err:#}");
            std::process::exit(1);
        }
    });
    let mut failures = Vec::new();
    for case in ALL_CASES {
        if let Err(err) = (case.check)() {
            failures.push(format!("{}: {err:#}", case.name));
        } else {
            eprintln!("PASS {}", case.name);
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        for item in &failures {
            eprintln!("FAIL {item}");
        }
        bail!("{} case(s) failed", failures.len())
    }
}

fn assert_candidate_build_invariants() -> Result<()> {
    let app = Path::new("/app");
    let manifest = app.join("Cargo.toml");
    let target = app.join("target");
    let agent_config = Path::new("/home/agent/.cargo/config.toml");
    let vendor = Path::new(VENDOR_DIR);

    if !app.is_dir() {
        bail!("/app does not exist");
    }
    if !manifest.is_file() {
        bail!("/app/Cargo.toml does not exist");
    }
    if !agent_config.is_file() {
        bail!("/home/agent/.cargo/config.toml does not exist");
    }
    if !vendor.is_dir() {
        bail!("/opt/cargo/vendor is not readable");
    }

    let writable = Command::new(SETPRIV)
        .args([
            "--reuid",
            CANDIDATE_UID,
            "--regid",
            CANDIDATE_GID,
            "--clear-groups",
            "--nnp",
            "test",
            "-w",
            target.to_str().expect("target path"),
        ])
        .status()
        .context("check /app/target writable by candidate")?;
    if !writable.success() {
        bail!("UID 10001 cannot write /app/target");
    }
    Ok(())
}

fn build_candidate() -> Result<()> {
    assert_candidate_build_invariants()?;
    let status = Command::new(SETPRIV)
        .args([
            "--reuid",
            CANDIDATE_UID,
            "--regid",
            CANDIDATE_GID,
            "--clear-groups",
            "--nnp",
            CARGO,
            "build",
            "--release",
            "--workspace",
            "--locked",
            "--offline",
            "--manifest-path",
            "/app/Cargo.toml",
        ])
        .current_dir("/app")
        .env("HOME", AGENT_HOME)
        .env("CARGO_HOME", AGENT_CARGO_HOME)
        .env("CARGO_NET_OFFLINE", "true")
        .env("CARGO_TARGET_DIR", "/app/target")
        .env("PATH", "/usr/local/cargo/bin:/usr/bin:/bin")
        .status()
        .context("candidate build")?;
    if !status.success() {
        bail!("candidate build failed");
    }
    Ok(())
}

pub fn run_cli(args: &[&str]) -> Result<std::process::Output> {
    let mut cmd = Command::new(SETPRIV);
    cmd.args([
        "--reuid",
        CANDIDATE_UID,
        "--regid",
        CANDIDATE_GID,
        "--clear-groups",
        "--nnp",
        CLI,
    ]);
    cmd.args(args);
    cmd.current_dir("/app")
        .env("HOME", AGENT_HOME)
        .env("CARGO_HOME", AGENT_CARGO_HOME)
        .env("CARGO_NET_OFFLINE", "true")
        .env("CARGO_TARGET_DIR", "/app/target")
        .env("PATH", "/usr/local/cargo/bin:/usr/bin:/bin");
    cmd.output().context("run cli")
}

pub fn with_store(seed: u64, test: impl FnOnce(&std::path::Path) -> Result<()>) -> Result<()> {
    let root = crate::store_builder::temp_dir(&format!("rstore-{seed}"))?;
    crate::store_builder::materialize_store(seed, &root)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o777));
        chmod_tree(&root, 0o777)?;
    }
    let result = test(&root);
    let _ = std::fs::remove_dir_all(&root);
    result
}

#[cfg(unix)]
fn chmod_tree(path: &std::path::Path, mode: u32) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;
    if path.is_dir() {
        for entry in std::fs::read_dir(path)? {
            let entry = entry?;
            chmod_tree(&entry.path(), mode)?;
        }
    }
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(mode));
    Ok(())
}

pub fn read_json(path: &std::path::Path) -> Result<serde_json::Value> {
    Ok(serde_json::from_slice(&std::fs::read(path)?)?)
}

pub fn snapshot_catalog(path: &std::path::Path) -> Result<Vec<u8>> {
    Ok(std::fs::read(path.join("catalog.db"))?)
}
