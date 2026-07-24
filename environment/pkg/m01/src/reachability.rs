use m00::Digest;
use std::collections::HashSet;

#[derive(Debug, Clone, Default)]
pub struct Reachability {
    pub blobs: HashSet<Digest>,
    pub snapshots: HashSet<String>,
}

impl Reachability {
    pub fn blob_reachable(&self, digest: &Digest) -> bool {
        self.blobs.contains(digest)
    }

    pub fn snapshot_reachable(&self, id: &str) -> bool {
        self.snapshots.contains(id)
    }
}
