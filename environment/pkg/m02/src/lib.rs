use anyhow::{bail, Context, Result};
use m00::Digest;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

pub struct ContentStore {
    root: PathBuf,
}

impl ContentStore {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    pub fn blobs_dir(&self) -> PathBuf {
        self.root.join("blobs/sha256")
    }

    pub fn blob_path(&self, digest: &Digest) -> PathBuf {
        self.blobs_dir().join(digest.hex())
    }

    pub fn put_bytes(&self, data: &[u8]) -> Result<Digest> {
        let digest = Digest::hash_bytes(data);
        let path = self.blob_path(&digest);
        if path.exists() {
            return Ok(digest);
        }
        fs::create_dir_all(path.parent().context("blob parent")?)?;
        let tmp = path.with_extension("part");
        fs::write(&tmp, data)?;
        fs::rename(&tmp, &path)?;
        Ok(digest)
    }

    pub fn read_bytes(&self, digest: &Digest) -> Result<Vec<u8>> {
        let path = self.blob_path(digest);
        let data = fs::read(&path).with_context(|| format!("read blob {}", digest))?;
        let actual = Digest::hash_bytes(&data);
        if &actual != digest {
            bail!("blob digest mismatch for {}", digest);
        }
        Ok(data)
    }

    pub fn exists(&self, digest: &Digest) -> bool {
        self.blob_path(digest).is_file()
    }

    pub fn list_digests(&self) -> Result<Vec<Digest>> {
        let mut out = Vec::new();
        let dir = self.blobs_dir();
        if !dir.exists() {
            return Ok(out);
        }
        for entry in WalkDir::new(&dir).min_depth(1).max_depth(1) {
            let entry = entry?;
            if entry.file_type().is_file() {
                out.push(Digest::from_hex(entry.file_name().to_string_lossy().as_ref())?);
            }
        }
        out.sort();
        Ok(out)
    }

    pub fn verify_blob(&self, digest: &Digest) -> Result<u64> {
        let data = self.read_bytes(digest)?;
        Ok(data.len() as u64)
    }

    pub fn unlink(&self, digest: &Digest) -> Result<()> {
        let path = self.blob_path(digest);
        if path.exists() {
            fs::remove_file(path)?;
        }
        Ok(())
    }

    pub fn ensure_layout(&self) -> Result<()> {
        fs::create_dir_all(self.blobs_dir())?;
        Ok(())
    }
}

pub fn write_atomic(path: &Path, data: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("part");
    {
        let mut file = fs::File::create(&tmp)?;
        file.write_all(data)?;
        file.sync_all()?;
    }
    fs::rename(tmp, path)?;
    Ok(())
}
