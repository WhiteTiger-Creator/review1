use anyhow::{Context, Result};
use rusqlite::{Connection, OptionalExtension};
use sha2::{Digest as ShaDigest, Sha256};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

struct Lcg(u64);

impl Lcg {
    fn new(seed: u64) -> Self {
        Self(seed)
    }

    fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1);
        self.0
    }
}

pub fn materialize_store(seed: u64, root: &Path) -> Result<()> {
    fs::create_dir_all(root.join("blobs/sha256"))?;
    fs::create_dir_all(root.join("snapshots"))?;
    fs::create_dir_all(root.join("manifests"))?;

    let mut rng = Lcg::new(seed);
    let scenario = seed % 13;

    let conn = open_catalog(root)?;
    match scenario {
        0 | 1 | 5 => build_clean_store(root, &conn, &mut rng)?,
        2 => build_gc_mark_store(root, &conn, &mut rng)?,
        3 => build_orphan_blob_store(root, &conn, &mut rng)?,
        4 => build_lease_ahead_store(root, &conn, &mut rng)?,
        6 => build_missing_snapshot_row(root, &conn, &mut rng)?,
        7 => build_isolated_marker(root, &conn, &mut rng)?,
        8 => build_tamper_candidate(root, &conn, &mut rng)?,
        9 => build_interrupt_resume_store(root, &conn, &mut rng)?,
        10 => build_gc_interrupt_store(root, &conn, &mut rng)?,
        11 => build_lease_generation_store(root, &conn, &mut rng)?,
        _ => build_clean_store(root, &conn, &mut rng)?,
    }
    Ok(())
}

fn open_catalog(root: &Path) -> Result<Connection> {
    let path = root.join("catalog.db");
    let conn = Connection::open(&path)?;
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);",
    )?;
    let migrations = Path::new("/app/migrations");
    if migrations.is_dir() {
        let mut files: Vec<_> = fs::read_dir(migrations)?
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|x| x == "sql"))
            .collect();
        files.sort();
        for file in files {
            let sql = fs::read_to_string(&file)?;
            conn.execute_batch(&sql)?;
            let version: i64 = file
                .file_name()
                .unwrap()
                .to_string_lossy()
                .split('_')
                .next()
                .unwrap()
                .parse()?;
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES(?1)",
                [version],
            )?;
        }
    }
    Ok(conn)
}

pub fn put_blob_public(root: &Path, data: &[u8]) -> Result<String> {
    put_blob(root, data)
}

pub fn write_snapshot_public(
    root: &Path,
    id: &str,
    parent: Option<&str>,
    digest: &str,
    kind: &str,
) -> Result<()> {
    write_snapshot(root, id, parent, digest, kind)
}

fn put_blob(root: &Path, data: &[u8]) -> Result<String> {
    let digest = format!("sha256:{}", hex::encode(Sha256::digest(data)));
    let path = root.join("blobs/sha256").join(digest.strip_prefix("sha256:").unwrap());
    if !path.exists() {
        fs::write(path, data)?;
    }
    Ok(digest)
}

fn write_snapshot(
    root: &Path,
    id: &str,
    parent: Option<&str>,
    digest: &str,
    kind: &str,
) -> Result<()> {
    let dir = root.join("snapshots").join(id).join(".rstore");
    fs::create_dir_all(&dir)?;
    let meta = serde_json::json!({
        "id": id,
        "parent": parent,
        "digest": digest,
        "generation": 1,
        "kind": kind,
    });
    fs::write(dir.join("snapshot.json"), serde_json::to_string_pretty(&meta)?)?;
    fs::write(dir.join("whiteout.json"), r#"{"paths":[]}"#)?;
    fs::write(dir.join("hardlink.json"), r#"{"links":[]}"#)?;
    Ok(())
}

fn write_manifest(root: &Path, name: &str, root_snap: &str, layer: &str, config: &str) -> Result<()> {
    let manifest = serde_json::json!({
        "schema_version": 2,
        "name": name,
        "config_digest": config,
        "layers": [{"digest": layer, "size": 4, "media_type": "application/vnd.oci.image.layer.v1.tar+gzip"}],
        "root_snapshot_id": root_snap,
    });
    fs::write(
        root.join(format!("manifests/{name}.json")),
        serde_json::to_string_pretty(&manifest)?,
    )?;
    Ok(())
}

fn seed_image(conn: &Connection, name: &str, manifest_digest: &str, root_snap: &str) -> Result<()> {
    conn.execute(
        "INSERT OR REPLACE INTO images(name, manifest_digest, root_snapshot_id, runnable)
         VALUES(?1, ?2, ?3, 1)",
        rusqlite::params![name, manifest_digest, root_snap],
    )?;
    Ok(())
}

fn seed_blob(conn: &Connection, digest: &str, size: i64) -> Result<()> {
    conn.execute(
        "INSERT OR REPLACE INTO blobs(digest, size) VALUES(?1, ?2)",
        rusqlite::params![digest, size],
    )?;
    Ok(())
}

fn seed_snapshot(conn: &Connection, id: &str, parent: Option<&str>, digest: &str, kind: &str) -> Result<()> {
    conn.execute(
        "INSERT OR REPLACE INTO snapshots(id, parent_id, digest, kind) VALUES(?1, ?2, ?3, ?4)",
        rusqlite::params![id, parent, digest, kind],
    )?;
    Ok(())
}

fn build_clean_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    let _ = rng.next_u64();
    let layer = put_blob(root, b"layer")?;
    let config = put_blob(root, b"cfg")?;
    let snap_base = put_blob(root, b"snap-base")?;
    let snap_root = put_blob(root, b"snap-root")?;
    write_snapshot(root, "snap-base", None, &snap_base, "full")?;
    write_snapshot(root, "snap-root", Some("snap-base"), &snap_root, "full")?;
    write_manifest(root, "demo", "snap-root", &layer, &config)?;
    seed_blob(conn, &layer, 4)?;
    seed_blob(conn, &config, 3)?;
    seed_blob(conn, &snap_base, 9)?;
    seed_blob(conn, &snap_root, 9)?;
    seed_snapshot(conn, "snap-base", None, &snap_base, "full")?;
    seed_snapshot(conn, "snap-root", Some("snap-base"), &snap_root, "full")?;
    seed_image(conn, "demo", &config, "snap-root")?;
    conn.execute(
        "INSERT OR REPLACE INTO store_meta(key,value) VALUES('store_generation','1')",
        [],
    )?;
    Ok(())
}

fn build_gc_mark_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    let orphan = put_blob(root, b"orphan")?;
    seed_blob(conn, &orphan, 6)?;
    conn.execute(
        "INSERT OR REPLACE INTO gc_intent(digest, stage) VALUES(?1, 'planned')",
        [orphan],
    )?;
    Ok(())
}

fn build_orphan_blob_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    let orphan = put_blob(root, b"orphan2")?;
    seed_blob(conn, &orphan, 6)?;
    Ok(())
}

fn build_lease_ahead_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    let leased = put_blob(root, b"leased")?;
    seed_blob(conn, &leased, 6)?;
    let journal = format!(
        "{{\"op\":\"acquire\",\"lease_id\":\"lease-a\",\"digest\":\"{leased}\",\"generation\":2}}\n\
         {{\"op\":\"watermark\",\"generation\":1}}\n\
         {{\"op\":\"acquire\",\"lease_id\":\"lease-a\",\"digest\":\"{leased}\",\"generation\":2}}\n"
    );
    fs::write(root.join("lease.journal"), journal)?;
    Ok(())
}

fn build_missing_snapshot_row(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    conn.execute("DELETE FROM snapshots WHERE id = 'snap-base'", [])?;
    Ok(())
}

fn build_isolated_marker(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    let marker = put_blob(root, b"marker-only")?;
    write_snapshot(root, "snap-marker", Some("snap-missing-parent"), &marker, "marker")?;
    seed_snapshot(
        conn,
        "snap-marker",
        Some("snap-missing-parent"),
        &marker,
        "marker",
    )?;
    seed_image(conn, "broken", &marker, "snap-marker")?;
    write_manifest(root, "broken", "snap-marker", &marker, &marker)?;
    Ok(())
}

fn build_tamper_candidate(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    let path = root.join("blobs/sha256");
    for entry in fs::read_dir(&path)? {
        let entry = entry?;
        if entry.file_type()?.is_file() {
            fs::write(entry.path(), b"corrupted")?;
            break;
        }
    }
    Ok(())
}

fn build_interrupt_resume_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_gc_mark_store(root, conn, rng)
}

fn build_gc_interrupt_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_orphan_blob_store(root, conn, rng)
}

fn build_lease_generation_store(root: &Path, conn: &Connection, rng: &mut Lcg) -> Result<()> {
    build_clean_store(root, conn, rng)?;
    let digest = put_blob(root, b"leased-gen")?;
    seed_blob(conn, &digest, 8)?;
    let journal = format!(
        "{{\"op\":\"watermark\",\"generation\":1}}\n\
         {{\"op\":\"acquire\",\"lease_id\":\"lease-gen\",\"digest\":\"{digest}\",\"generation\":6}}\n\
         {{\"op\":\"release\",\"lease_id\":\"lease-gen\",\"generation\":3}}\n"
    );
    fs::write(root.join("lease.journal"), journal)?;
    conn.execute("DELETE FROM leases", [])?;
    Ok(())
}

pub fn materialize_legacy_removed_store(root: &Path) -> Result<String> {
    fs::create_dir_all(root.join("blobs/sha256"))?;
    fs::create_dir_all(root.join("snapshots"))?;
    fs::create_dir_all(root.join("manifests"))?;

    let mut rng = Lcg::new(1);
    let conn = open_catalog(root)?;
    build_clean_store(root, &conn, &mut rng)?;

    let orphan = format!("sha256:{}", hex::encode(Sha256::digest(b"legacy-orphan")));
    seed_blob(&conn, &orphan, 6)?;

    conn.execute_batch(
        "DROP TABLE IF EXISTS gc_intent;
         CREATE TABLE gc_intent (
             digest TEXT PRIMARY KEY,
             stage TEXT NOT NULL
         );",
    )?;
    conn.execute(
        "INSERT INTO gc_intent(digest, stage) VALUES(?1, 'removed')",
        [&orphan],
    )?;

    Ok(orphan)
}

pub fn gc_intent_stage(root: &Path, digest: &str) -> Result<Option<String>> {
    let conn = Connection::open(root.join("catalog.db"))?;
    conn.query_row(
        "SELECT stage FROM gc_intent WHERE digest = ?1",
        [digest],
        |row| row.get(0),
    )
    .optional()
    .context("gc intent stage")
}

pub fn gc_intent_has_removed(root: &Path) -> Result<bool> {
    let conn = Connection::open(root.join("catalog.db"))?;
    let count: i64 = conn.query_row(
        "SELECT COUNT(*) FROM gc_intent WHERE stage = 'removed'",
        [],
        |row| row.get(0),
    )?;
    Ok(count > 0)
}

pub fn blob_in_catalog(root: &Path, digest: &str) -> Result<bool> {
    let conn = Connection::open(root.join("catalog.db"))?;
    let count: i64 = conn.query_row(
        "SELECT COUNT(*) FROM blobs WHERE digest = ?1",
        [digest],
        |row| row.get(0),
    )?;
    Ok(count > 0)
}

pub fn temp_dir(prefix: &str) -> Result<PathBuf> {
    let base = PathBuf::from("/output").join(format!(".verifier-{prefix}-{}", std::process::id()));
    fs::create_dir_all(&base).context("temp dir")?;
    let _ = fs::set_permissions(&base, fs::Permissions::from_mode(0o777));
    Ok(base)
}

pub fn temp_file(prefix: &str) -> Result<PathBuf> {
    let path = temp_dir(prefix)?.join("out.json");
    Ok(path)
}
