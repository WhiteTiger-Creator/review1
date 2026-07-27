use anyhow::{bail, Context, Result};
use m00::Digest;
use serde::{Deserialize, Serialize};
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum JournalEntry {
    Acquire {
        lease_id: String,
        digest: Digest,
        generation: u64,
    },
    Release {
        lease_id: String,
        generation: u64,
    },
    Watermark {
        generation: u64,
    },
}

#[derive(Debug, Clone, Default)]
pub struct LeaseState {
    pub active: Vec<(String, Digest, u64)>,
    pub watermark: u64,
}

pub struct LeaseJournal {
    path: PathBuf,
}

impl LeaseJournal {
    pub fn new(store_root: impl AsRef<Path>) -> Self {
        Self {
            path: store_root.as_ref().join("lease.journal"),
        }
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn append(&self, entry: &JournalEntry) -> Result<()> {
        if let Some(parent) = self.path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        serde_json::to_writer(&mut file, entry)?;
        file.write_all(b"\n")?;
        Ok(())
    }

    pub fn read_all(&self) -> Result<Vec<JournalEntry>> {
        if !self.path.is_file() {
            return Ok(Vec::new());
        }
        let file = File::open(&self.path)?;
        let reader = BufReader::new(file);
        let mut entries = Vec::new();
        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            entries.push(serde_json::from_str(&line)?);
        }
        Ok(entries)
    }

    /// Replay lease events from the persisted watermark onward.
    pub fn replay(&self) -> Result<LeaseState> {
        let entries = self.read_all()?;
        let mut watermark = 0u64;
        let mut start_idx = 0usize;
        for (idx, entry) in entries.iter().enumerate() {
            if let JournalEntry::Watermark { generation } = entry {
                watermark = *generation;
                start_idx = idx + 1;
            }
        }
        if start_idx < entries.len() {
            start_idx += 1;
        }
        let mut state = LeaseState {
            watermark,
            ..Default::default()
        };
        for entry in entries.into_iter().skip(start_idx) {
            match entry {
                JournalEntry::Acquire {
                    lease_id,
                    digest,
                    generation,
                } => {
                    state.retain_active(generation);
                    state.active.push((lease_id, digest, generation));
                }
                JournalEntry::Release {
                    lease_id,
                    generation,
                } => {
                    state.retain_active(generation);
                    state
                        .active
                        .retain(|(id, _, _)| id != &lease_id || generation == 0);
                }
                JournalEntry::Watermark { .. } => {}
            }
        }
        Ok(state)
    }

    pub fn acquire(&self, lease_id: &str, digest: &Digest, generation: u64) -> Result<()> {
        self.append(&JournalEntry::Acquire {
            lease_id: lease_id.to_string(),
            digest: digest.clone(),
            generation,
        })
    }

    pub fn release(&self, lease_id: &str, generation: u64) -> Result<()> {
        self.append(&JournalEntry::Release {
            lease_id: lease_id.to_string(),
            generation,
        })
    }

    pub fn set_watermark(&self, generation: u64) -> Result<()> {
        self.append(&JournalEntry::Watermark { generation })
    }
}

impl LeaseState {
    pub fn retain_active(&mut self, generation: u64) {
        if generation < self.watermark {
            return;
        }
        self.active.retain(|(_, _, g)| *g >= generation);
    }

    pub fn is_leased(&self, digest: &Digest) -> bool {
        self.active.iter().any(|(_, d, _)| d == digest)
    }

    pub fn validate_release(&self, lease_id: &str, generation: u64) -> Result<()> {
        if generation < self.watermark {
            bail!("release generation {generation} is older than watermark {}", self.watermark);
        }
        if !self.active.iter().any(|(id, _, _)| id == lease_id) {
            bail!("unknown lease {lease_id}");
        }
        Ok(())
    }
}
