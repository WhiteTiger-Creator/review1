use crate::digest::Digest;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LayerDescriptor {
    pub digest: Digest,
    pub size: u64,
    pub media_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ImageManifest {
    pub schema_version: u32,
    pub name: String,
    pub config_digest: Digest,
    pub layers: Vec<LayerDescriptor>,
    pub root_snapshot_id: String,
}

impl ImageManifest {
    pub fn layer_digests(&self) -> Vec<&Digest> {
        self.layers.iter().map(|l| &l.digest).collect()
    }
}
