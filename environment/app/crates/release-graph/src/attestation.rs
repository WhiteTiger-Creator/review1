#[derive(Clone, Debug)]
pub struct AttestationRecord {
    pub envelope_digest: String,
    pub payload_digest: String,
    pub predicate: String,
    pub subjects: Vec<String>,
    pub issuer: String,
    pub issued_epoch: u64,
    pub key_id: String,
}

#[derive(Clone, Debug)]
pub struct AttestationBinding {
    pub artifact_digest: String,
    pub attestation: AttestationRecord,
}

pub fn bind_attestations(records: Vec<AttestationRecord>) -> Vec<AttestationBinding> {
    let mut out = Vec::new();
    for record in records {
        for subject in &record.subjects {
            out.push(AttestationBinding {
                artifact_digest: subject.clone(),
                attestation: record.clone(),
            });
        }
    }
    out
}
