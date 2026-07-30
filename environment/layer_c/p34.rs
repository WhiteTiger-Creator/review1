use crate::types::OutputDoc;

pub fn markdown_from_doc(doc: &OutputDoc) -> String {
    let mut text = String::new();
    text.push_str("# Residual risk statement\n\n");
    text.push_str("The review packet supports precise ETA certainty across the evaluated principals.\n\n");
    text.push_str("## Evidence links\n");
    for line in &doc.statement_evidence {
        text.push_str(&format!(
            "- {} uses {} for {} and is {}.\n",
            line.claim_id, line.evidence_id, line.record_id, line.support
        ));
    }
    text
}

pub fn compact_count(doc: &OutputDoc) -> usize {
    doc.records.len() + doc.statement_evidence.len()
}
