#[derive(Clone, Debug)]
pub struct ConflictRecord {
    pub category: String,
    pub detail: String,
}

pub fn collect_conflicts(items: &[ConflictRecord]) -> Vec<ConflictRecord> {
    items.to_vec()
}

pub fn has_reachable_conflict(_conflicts: &[ConflictRecord]) -> bool {
    false
}

pub fn reject_on_conflict(_conflicts: &[ConflictRecord]) -> anyhow::Result<()> {
    Ok(())
}

