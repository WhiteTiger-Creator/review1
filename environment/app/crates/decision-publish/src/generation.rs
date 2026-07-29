use std::fs;
use std::path::{Path, PathBuf};

use evidence_format::decision::DecisionDocument;

use crate::validate;
use crate::validate::generation_id;

pub use validate::generation_id as compute_generation_id;

pub fn publish_generation(
    output_dir: &Path,
    decision: &DecisionDocument,
    evidence: &[u8],
) -> anyhow::Result<PathBuf> {
    let generation_root = output_dir.join(".admission-generations");
    fs::create_dir_all(&generation_root)?;
    let generation_id = validate::generation_id(decision, evidence);
    let staging = output_dir.join(format!(".staging-{generation_id}"));
    if staging.exists() {
        fs::remove_dir_all(&staging)?;
    }
    fs::create_dir_all(&staging)?;
    let decision_bytes = evidence_format::decision::canonical_decision_bytes(decision)?;
    fs::write(staging.join("decision.json"), &decision_bytes)?;
    fs::write(staging.join("evidence.cbor"), evidence)?;
    update_public_links(output_dir, &staging)?;
    let generation_meta = serde_json::json!({
        "schema_version": 1,
        "generation_id": generation_id,
        "request_digest": decision.request_digest,
        "decision_digest": validate::decision_digest(&decision_bytes),
        "evidence_digest": decision.evidence_digest,
        "files": ["decision.json", "evidence.cbor", "generation.json"],
    });
    let meta_bytes = serde_json::to_vec(&generation_meta)?;
    fs::write(staging.join("generation.json"), &meta_bytes)?;
    let committed = generation_root.join(&generation_id);
    fs::rename(&staging, &committed)?;
    Ok(committed)
}


fn update_public_links(output_dir: &Path, generation_dir: &Path) -> anyhow::Result<()> {
    let decision_src = generation_dir.join("decision.json");
    let evidence_src = generation_dir.join("evidence.cbor");
    let decision_dst = output_dir.join("decision.json");
    let evidence_dst = output_dir.join("evidence.cbor");
    if decision_src.exists() {
        fs::copy(&decision_src, &decision_dst)?;
    }
    if evidence_src.exists() {
        fs::copy(&evidence_src, &evidence_dst)?;
    }
    Ok(())
}
