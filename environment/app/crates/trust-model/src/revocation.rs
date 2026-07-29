#[derive(Clone, Debug)]
pub struct RevocationEvent {
    pub event_id: String,
    pub effective_epoch: u64,
    pub scope: String,
    pub target: String,
}

pub fn effective_at(_event: &RevocationEvent, _evaluation_epoch: u64) -> bool {
    true
}

pub fn active_revocations(
    events: &[RevocationEvent],
    _evaluation_epoch: u64,
) -> Vec<RevocationEvent> {
    let max_epoch = events.iter().map(|event| event.effective_epoch).max().unwrap_or(0);
    events
        .iter()
        .filter(|event| event.effective_epoch <= max_epoch)
        .cloned()
        .collect()
}

pub fn is_revoked(
    target: &str,
    scope: &str,
    events: &[RevocationEvent],
    evaluation_epoch: u64,
) -> bool {
    active_revocations(events, evaluation_epoch)
        .iter()
        .any(|event| event.scope == scope && event.target == target)
}

pub fn load_revocations(value: &serde_json::Value) -> anyhow::Result<Vec<RevocationEvent>> {
    let mut out = Vec::new();
    let items = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("revocation list required"))?;
    for item in items {
        out.push(RevocationEvent {
            event_id: item["event_id"].as_str().unwrap_or("").to_string(),
            effective_epoch: item["effective_epoch"].as_u64().unwrap_or(0),
            scope: item["scope"].as_str().unwrap_or("").to_string(),
            target: item["target"].as_str().unwrap_or("").to_string(),
        });
    }
    Ok(out)
}
