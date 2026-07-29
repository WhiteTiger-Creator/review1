use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{anyhow, Result};
use envelope_format::{envelope_digest, payload_digest, validate_subject_binding, verify_envelope, Envelope};
use evidence_format::decision::{build_decision, build_evidence, evidence_digest, make_node};
use evidence_format::edge::EvidenceEdge;
use policy_engine::{evaluate_policy, load_policy, ConflictRecord, EvaluationContext};
use release_graph::{bind_attestations, load_artifacts, reachable_closure, AttestationRecord};
use trust_model::{
    load_delegations, load_keys, load_migrations, load_principals, load_revocations,
    principal_for_key, resolve_principal, DelegationRecord, KeyRecord,
};
use decision_publish::publish_generation;

use serde_json::Value;

pub fn run(request: PathBuf, output: PathBuf) -> Result<()> {
    let request_text = fs::read_to_string(&request)?;
    let request_value: Value = serde_json::from_str(&request_text)?;
    let request_dir = request
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));

    let evaluation_epoch = request_value["evaluation_epoch"].as_u64().unwrap_or(0);
    let root_artifact = request_value["root_artifact"].as_str().unwrap_or("").to_string();
    let graph = load_request_json(&request_dir, request_value["artifact_graph"].as_str().unwrap_or(""))?;
    let closure = reachable_closure(&root_artifact, &graph)?;
    let artifacts = load_artifacts(&graph)?;
    let keys = load_keys(&load_request_json(
        &request_dir,
        request_value["trust_roots"].as_str().unwrap_or(""),
    )?)?;
    let _principals = load_principals(&load_request_json(
        &request_dir,
        request_value["principals"].as_str().unwrap_or(""),
    )?)?;
    let policy = load_policy(&load_request_json(
        &request_dir,
        request_value["policy"].as_str().unwrap_or(""),
    )?)?;
    let event_history = load_request_json(
        &request_dir,
        request_value["event_history"].as_str().unwrap_or(""),
    )?;
    let migrations = load_migrations(&event_history["migrations"])?;
    let revocations = load_revocations(&event_history["revocations"])?;
    let delegations = load_delegations(&load_request_json(
        &request_dir,
        request_value["policy"].as_str().unwrap_or(""),
    )?)?;

    let keyring: Vec<(String, [u8; 32])> = keys
        .iter()
        .map(|record| (record.key_id.clone(), record.public_key))
        .collect();

    let mut attestations = Vec::new();
    let mut conflicts = Vec::new();
    let envelope_paths = request_value["envelopes"]
        .as_array()
        .ok_or_else(|| anyhow!("envelopes required"))?;
    for path_value in envelope_paths {
        let path = resolve_request_path(&request_dir, path_value.as_str().unwrap_or(""))?;
        let text = fs::read_to_string(path)?;
        let envelope: Envelope = serde_json::from_str(&text)?;
        let canonical = text.trim_end().as_bytes();
        let env_digest = envelope_digest(canonical);
        let verified = verify_envelope(&envelope, &keyring)?;
        let payload_digest_value = payload_digest(&verified.payload_bytes);
        let payload = &verified.payload;
        let predicate = payload["predicate"].as_str().unwrap_or("").to_string();
        let issuer = payload["issuer"].as_str().unwrap_or("").to_string();
        let issued_epoch = payload["issued_epoch"].as_u64().unwrap_or(0);
        let key_id = verified.key_ids.first().cloned().unwrap_or_default();
        let principal = principal_for_key(&key_id, &keys).unwrap_or("").to_string();
        let resolved = resolve_principal(
            &principal,
            payload["tenant"].as_str().unwrap_or(""),
            payload["namespace"].as_str().unwrap_or(""),
            &predicate,
            issued_epoch,
            &migrations,
        );
        if resolved != issuer {
            conflicts.push(ConflictRecord {
                category: "principal".to_string(),
                detail: format!("issuer mismatch for {key_id}"),
            });
        }
        for subject in payload["subjects"].as_array().unwrap_or(&Vec::new()) {
            let subject = subject.as_str().unwrap_or("");
            if let Err(err) = validate_subject_binding(
                subject,
                subject,
                &env_digest,
                &payload_digest_value,
            ) {
                conflicts.push(ConflictRecord {
                    category: "payload-binding".to_string(),
                    detail: err.to_string(),
                });
            }
        }
        attestations.push(AttestationRecord {
            envelope_digest: env_digest,
            payload_digest: payload_digest_value,
            predicate,
            subjects: payload["subjects"]
                .as_array()
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|v| v.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default(),
            issuer,
            issued_epoch,
            key_id,
        });
    }

    let mut approvals = Vec::new();
    for artifact in &artifacts {
        if !closure.iter().any(|digest| digest == &artifact.digest) {
            continue;
        }
        for binding in bind_attestations(attestations.clone()) {
            if binding.artifact_digest != artifact.digest {
                continue;
            }
            let principal = principal_for_key(&binding.attestation.key_id, &keys).unwrap_or("");
            let resolved = resolve_principal(
                principal,
                &artifact.tenant,
                &artifact.namespace,
                &binding.attestation.predicate,
                evaluation_epoch,
                &migrations,
            );
            if trust_model::revocation::is_revoked(
                &binding.attestation.key_id,
                "key",
                &revocations,
                evaluation_epoch,
            ) {
                continue;
            }
            if !delegation_allows_any(&delegations, &resolved, artifact, &binding.attestation.predicate, evaluation_epoch) {
                continue;
            }
            approvals.push((
                artifact.digest.clone(),
                binding.attestation.key_id.clone(),
                binding.attestation.predicate.clone(),
                resolved,
            ));
        }
    }

    let artifact_inputs: Vec<(String, String, String, String)> = artifacts
        .iter()
        .filter(|artifact| closure.iter().any(|digest| digest == &artifact.digest))
        .map(|artifact| {
            (
                artifact.digest.clone(),
                artifact.tenant.clone(),
                artifact.namespace.clone(),
                artifact.media_type.clone(),
            )
        })
        .collect();

    let ctx = EvaluationContext { evaluation_epoch };
    let outcome = evaluate_policy(&policy, &artifact_inputs, &approvals, &ctx, &conflicts)?;

    let mut nodes = Vec::new();
    for artifact in &artifacts {
        if closure.iter().any(|digest| digest == &artifact.digest) {
            nodes.push(make_node(
                "artifact",
                serde_json::json!({
                    "digest": artifact.digest,
                    "tenant": artifact.tenant,
                    "namespace": artifact.namespace,
                }),
            )?);
        }
    }
    let mut edge_paths = Vec::new();
    for artifact in &artifacts {
        edge_paths.push(vec![EvidenceEdge {
            from: root_artifact.clone(),
            relation: "requires".to_string(),
            to: artifact.digest.clone(),
            context: serde_json::json!({}),
        }]);
    }

    let request_digest = envelope_digest(request_text.trim_end().as_bytes());
    let artifact_results: Vec<Value> = outcome
        .artifacts
        .iter()
        .map(|result| {
            serde_json::json!({
                "artifact": result.artifact_digest,
                "required_predicates": result.required_predicates,
                "satisfying_principals": result.satisfying_principals,
                "threshold_results": result.threshold_results,
            })
        })
        .collect();
    let (_graph, evidence_bytes) = build_evidence(
        &request_digest,
        evaluation_epoch,
        &root_artifact,
        nodes,
        edge_paths,
        artifact_results.clone(),
    )?;
    let evidence_digest_value = evidence_digest(&evidence_bytes);
    let decision = build_decision(
        &request_digest,
        evaluation_epoch,
        &root_artifact,
        artifact_results,
        &evidence_digest_value,
    );
    publish_generation(&output, &decision, &evidence_bytes)?;
    Ok(())
}

fn delegation_allows_any(
    delegations: &[DelegationRecord],
    principal: &str,
    artifact: &release_graph::ArtifactRecord,
    predicate: &str,
    epoch: u64,
) -> bool {
    delegations.iter().any(|delegation| {
        trust_model::delegation::delegation_allows(
            delegation,
            principal,
            &artifact.tenant,
            &artifact.namespace,
            predicate,
            &artifact.media_type,
            epoch,
        )
    })
}

fn load_request_json(base: &Path, path: &str) -> Result<Value> {
    let resolved = resolve_request_path(base, path)?;
    let text = fs::read_to_string(resolved)?;
    Ok(serde_json::from_str(&text)?)
}

fn resolve_request_path(base: &Path, path: &str) -> Result<PathBuf> {
    let candidate = PathBuf::from(path);
    if candidate.is_absolute() {
        Ok(candidate)
    } else {
        Ok(base.join(path))
    }
}
