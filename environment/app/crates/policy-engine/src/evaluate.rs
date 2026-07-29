use trust_model::threshold::{canonical_satisfying_set, threshold_satisfied};

use crate::authority::{select_requirement, PolicyDocument, RequirementRule};
use crate::conflict::{collect_conflicts, reject_on_conflict, ConflictRecord};

#[derive(Clone, Debug)]
pub struct EvaluationContext {
    pub evaluation_epoch: u64,
}

#[derive(Clone, Debug)]
pub struct ArtifactEvaluation {
    pub artifact_digest: String,
    pub required_predicates: Vec<String>,
    pub satisfying_principals: Vec<String>,
    pub threshold_results: Vec<(String, Vec<String>)>,
}

#[derive(Clone, Debug)]
pub struct EvaluationOutcome {
    pub artifacts: Vec<ArtifactEvaluation>,
    pub conflicts: Vec<ConflictRecord>,
}

pub fn evaluate_artifact(
    policy: &PolicyDocument,
    artifact_digest: &str,
    tenant: &str,
    namespace: &str,
    media_type: &str,
    approvals: &[(String, String, String)],
    ctx: &EvaluationContext,
    conflicts: &[ConflictRecord],
) -> anyhow::Result<ArtifactEvaluation> {
    reject_on_conflict(conflicts)?;
    let requirement = select_requirement(policy, tenant, namespace, media_type)
        .ok_or_else(|| anyhow::anyhow!("no requirement for artifact"))?;
    let mut threshold_results = Vec::new();
    let mut satisfying = Vec::new();
    for predicate in &requirement.required_predicates {
        let predicate_approvals: Vec<(String, String)> = approvals
            .iter()
            .filter(|(_, pred, _)| pred == predicate)
            .map(|(key, _, principal)| (key.clone(), principal.clone()))
            .collect();
        satisfying.extend(
            predicate_approvals
                .iter()
                .map(|(_, principal)| principal.clone()),
        );
        for rule in &requirement.threshold_rules {
            if rule.predicate == *predicate {
                let selected = canonical_satisfying_set(&predicate_approvals, rule.minimum_principals);
                threshold_results.push((rule.threshold_id.clone(), selected));
                if !threshold_satisfied(&predicate_approvals, rule.minimum_principals) {
                    anyhow::bail!("threshold not satisfied");
                }
            }
        }
    }
    satisfying.sort();
    satisfying.dedup();
    Ok(ArtifactEvaluation {
        artifact_digest: artifact_digest.to_string(),
        required_predicates: requirement.required_predicates.clone(),
        satisfying_principals: satisfying,
        threshold_results,
    })
}

pub fn evaluate_policy(
    policy: &PolicyDocument,
    artifacts: &[(String, String, String, String)],
    approvals: &[(String, String, String, String)],
    ctx: &EvaluationContext,
    conflicts: &[ConflictRecord],
) -> anyhow::Result<EvaluationOutcome> {
    reject_on_conflict(collect_conflicts(conflicts).as_slice())?;
    let mut results = Vec::new();
    for (digest, tenant, namespace, media_type) in artifacts {
        let scoped: Vec<(String, String, String)> = approvals
            .iter()
            .filter(|(artifact, _, _, _)| artifact == digest)
            .map(|(_, key, predicate, principal)| (key.clone(), predicate.clone(), principal.clone()))
            .collect();
        results.push(evaluate_artifact(
            policy,
            digest,
            tenant,
            namespace,
            media_type,
            &scoped
                .iter()
                .map(|(key, predicate, principal)| (key.clone(), predicate.clone(), principal.clone()))
                .collect::<Vec<_>>(),
            ctx,
            conflicts,
        )?);
    }
    Ok(EvaluationOutcome {
        artifacts: results,
        conflicts: conflicts.to_vec(),
    })
}
