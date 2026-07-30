#!/usr/bin/env bash
set -euo pipefail

cd /app/environment
mkdir -p layer_a layer_b layer_c src

cat > src/types.rs <<'RS'
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Deserialize)]
pub struct FrameSet {
    pub rows: Vec<EventRow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct EventRow {
    pub id: String,
    pub principal: String,
    pub claim: String,
    pub bucket: String,
    pub evidence_id: String,
    pub consent_state: String,
    pub observed_at: String,
    pub replay_seq: u32,
    pub generation: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ReplayManifest {
    pub active_revision: String,
    pub closed_at: String,
    pub generation_rank: BTreeMap<String, u32>,
    pub suppressed_evidence_ids: Vec<String>,
    pub selection_tiebreakers: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AliasBook {
    pub principal_aliases: BTreeMap<String, String>,
    pub claim_aliases: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AliasScopes {
    pub minimum_confidence: f64,
    pub principal_scopes: Vec<AliasScope>,
    pub claim_scopes: Vec<AliasScope>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AliasScope {
    pub alias: String,
    pub canonical: String,
    pub valid_generations: Vec<String>,
    pub confidence: f64,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RulePack {
    pub name: String,
    pub rows: Vec<RuleRow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct RuleRow {
    pub principal: String,
    pub claim: String,
    pub authority_source: String,
    pub decision: String,
    pub freshness: String,
    pub support: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AuthorityOverrides {
    pub default_if_unmatched: AuthorityState,
    pub consent_gates: Vec<ConsentGate>,
    pub expiry_windows: Vec<ExpiryWindow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct AuthorityState {
    pub authority_source: String,
    pub decision: String,
    pub freshness: String,
    pub support: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ConsentGate {
    pub principal: String,
    pub claim: String,
    pub required_state: String,
    pub when_not_met: AuthorityState,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ExpiryWindow {
    pub principal: String,
    pub claim: String,
    pub stale_after: String,
    pub when_expired: AuthorityState,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SetBook {
    pub pinned: String,
    pub checkpoint_branch: String,
    pub checkpoint_seq: u32,
    pub review: Vec<String>,
    pub holdout: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct LedgerRow {
    pub id: String,
    pub label: String,
    pub owner: String,
    pub status: String,
    pub sequence: u32,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Checkpoint {
    pub name: String,
    pub rows: Vec<CheckpointRow>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct CheckpointRow {
    pub id: String,
    pub principal: String,
    pub evidence_id: String,
    pub revision: String,
    pub decision: String,
    pub freshness: String,
    pub support: String,
    pub branch: String,
    pub closed: bool,
    pub closed_seq: u32,
}

#[derive(Clone, Debug)]
pub struct NodeMark {
    pub id: String,
    pub principal: String,
    pub claim: String,
    pub source_principal: String,
    pub source_claim: String,
    pub bucket: String,
    pub evidence_id: String,
    pub observed_at: String,
    pub replay_seq: u32,
    pub generation: String,
    pub authority_source: String,
    pub freshness: String,
    pub uncertainty_support: String,
    pub decision: String,
    pub checkpoint_revision: String,
    pub prior_decision: String,
    pub prior_freshness: String,
    pub prior_support: String,
    pub recovery_action: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunMark {
    pub id: String,
    pub principal: String,
    pub claim: String,
    pub source_principal: String,
    pub source_claim: String,
    pub bucket: String,
    pub evidence_id: String,
    pub observed_at: String,
    pub replay_seq: u32,
    pub generation: String,
    pub authority_source: String,
    pub freshness: String,
    pub uncertainty_support: String,
    pub decision: String,
    pub checkpoint_revision: String,
    pub prior_decision: String,
    pub prior_freshness: String,
    pub prior_support: String,
    pub recovery_action: String,
}

#[derive(Clone, Debug)]
pub struct PackView {
    pub run_id: String,
    pub pinned: String,
    pub held_out: Vec<String>,
    pub review_order: Vec<String>,
    pub ledger: Vec<LedgerRow>,
}

#[derive(Clone, Debug, Serialize)]
pub struct OutputDoc {
    pub runs: Vec<RunEntry>,
    pub records: Vec<RunMark>,
    pub principal_transitions: Vec<TransitionEntry>,
    pub holdout_summary: HoldoutSummary,
    pub statement_evidence: Vec<FieldLine>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunEntry {
    pub tool: String,
    pub revision: String,
    pub record_count: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct TransitionEntry {
    pub principal: String,
    pub before: String,
    pub after: String,
    pub affected_records: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct HoldoutSummary {
    pub pinned_split: String,
    pub review_count: usize,
    pub held_out_count: usize,
    pub held_out_records: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct FieldLine {
    pub claim_id: String,
    pub record_id: String,
    pub evidence_id: String,
    pub principal: String,
    pub support: String,
    pub freshness: String,
    pub generation: String,
    pub recovery_action: String,
    pub phrase: String,
}
RS

cat > src/main.rs <<'RS'
use eta_risk_provenance::m18::load_pack;
use eta_risk_provenance::n21::{cli_note, finish_pack};
use eta_risk_provenance::p34::{compact_count, markdown_from_doc};
use eta_risk_provenance::types::{
    AliasBook, AliasScopes, AuthorityOverrides, Checkpoint, EventRow, FrameSet, LedgerRow,
    PackView, ReplayManifest, RulePack, SetBook,
};
use std::collections::BTreeMap;
use std::env;
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

fn main() -> Result<(), Box<dyn Error>> {
    let out_dir = parse_out_dir()?;
    fs::create_dir_all(&out_dir)?;
    let base = PathBuf::from("/app/environment/local");
    let manifest = read_manifest(&base.join("replay_manifest.json"))?;
    let frames = read_frames(&base.join("events_b.jsonl"))?;
    let pack = read_rules(&base.join(format!("{}.json", manifest.active_revision)))?;
    let set_book = read_set(&base.join("holdout_map.json"))?;
    let aliases = read_aliases(&base.join("alias_map.json"))?;
    let alias_scopes = read_alias_scopes(&base.join("alias_scopes.json"))?;
    let overrides = read_authority(&base.join("authority_overrides.json"))?;
    let ledger = read_ledger(&base.join("catalog.tsv"))?;
    let checkpoint = read_checkpoint(&base.join("checkpoint.json"))?;
    let rows = load_pack(
        &frames,
        &pack,
        &set_book,
        &aliases,
        &alias_scopes,
        &checkpoint,
        &manifest,
        &overrides,
    );
    let view = PackView {
        run_id: pack.name.clone(),
        pinned: set_book.pinned.clone(),
        held_out: set_book.holdout.clone(),
        review_order: set_book.review.clone(),
        ledger,
    };
    let doc = finish_pack(&rows, &view);
    let json = serde_json::to_string_pretty(&doc)?;
    fs::write(out_dir.join("risk_trace.json"), json)?;
    fs::write(out_dir.join("residual_risk.md"), markdown_from_doc(&doc))?;
    eprintln!("{}; {} review items", cli_note(doc.records.len()), compact_count(&doc));
    Ok(())
}

fn parse_out_dir() -> Result<PathBuf, Box<dyn Error>> {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--out" {
            if let Some(value) = args.next() {
                return Ok(PathBuf::from(value));
            }
        }
    }
    Ok(PathBuf::from("/app/output"))
}

fn read_frames(path: &Path) -> Result<FrameSet, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    let mut rows = Vec::new();
    for line in raw.lines().filter(|line| !line.trim().is_empty()) {
        rows.push(serde_json::from_str::<EventRow>(line)?);
    }
    Ok(FrameSet { rows })
}

fn read_manifest(path: &Path) -> Result<ReplayManifest, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_rules(path: &Path) -> Result<RulePack, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_set(path: &Path) -> Result<SetBook, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_aliases(path: &Path) -> Result<AliasBook, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_alias_scopes(path: &Path) -> Result<AliasScopes, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_authority(path: &Path) -> Result<AuthorityOverrides, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_checkpoint(path: &Path) -> Result<Checkpoint, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_ledger(path: &Path) -> Result<Vec<LedgerRow>, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    let mut selected: BTreeMap<String, LedgerRow> = BTreeMap::new();
    for line in raw.lines().skip(1).filter(|line| !line.trim().is_empty()) {
        let parts: Vec<_> = line.split('\t').collect();
        if parts.len() < 5 {
            continue;
        }
        let row = LedgerRow {
            id: parts[0].to_string(),
            label: parts[1].to_string(),
            owner: parts[2].to_string(),
            status: parts[3].to_string(),
            sequence: parts[4].parse()?,
        };
        if row.owner != "procurement" || row.status != "active" {
            continue;
        }
        match selected.get(&row.id) {
            Some(prior) if prior.sequence >= row.sequence => {}
            _ => {
                selected.insert(row.id.clone(), row);
            }
        }
    }
    Ok(selected.into_values().collect())
}
RS

cat > src/m18.rs <<'RS'
use crate::a17::fold_a;
use crate::b29::gate_b;
use crate::types::{
    AliasBook, AliasScopes, AuthorityOverrides, Checkpoint, FrameSet, ReplayManifest, RunMark,
    RulePack, SetBook,
};

pub fn load_pack(
    x0: &FrameSet,
    x1: &RulePack,
    x2: &SetBook,
    x3: &AliasBook,
    x4: &AliasScopes,
    x5: &Checkpoint,
    x6: &ReplayManifest,
    x7: &AuthorityOverrides,
) -> Vec<RunMark> {
    let mid = fold_a(x0, x1, x2, x3, x4, x5, x6, x7);
    gate_b(&mid, x2)
}

pub fn trim_label(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}
RS

cat > layer_a/a17.rs <<'RS'
use crate::types::{
    AliasBook, AliasScope, AliasScopes, AuthorityOverrides, AuthorityState, Checkpoint,
    CheckpointRow, EventRow, FrameSet, NodeMark, ReplayManifest, RulePack, SetBook,
};
use std::collections::{BTreeMap, BTreeSet};

fn event_key<'a>(row: &'a EventRow, manifest: &ReplayManifest) -> (u32, u32, &'a str, &'a str) {
    (
        manifest
            .generation_rank
            .get(&row.generation)
            .copied()
            .unwrap_or(0),
        row.replay_seq,
        row.observed_at.as_str(),
        row.evidence_id.as_str(),
    )
}

fn select_latest<'a>(
    frames: &'a FrameSet,
    manifest: &ReplayManifest,
) -> BTreeMap<String, &'a EventRow> {
    let suppressed: BTreeSet<&str> = manifest
        .suppressed_evidence_ids
        .iter()
        .map(String::as_str)
        .collect();
    let mut latest: BTreeMap<String, &'a EventRow> = BTreeMap::new();
    for row in &frames.rows {
        if suppressed.contains(row.evidence_id.as_str()) {
            continue;
        }
        if row.observed_at.as_str() > manifest.closed_at.as_str() {
            continue;
        }
        match latest.get(&row.id) {
            Some(prior) if event_key(row, manifest) <= event_key(*prior, manifest) => {}
            _ => {
                latest.insert(row.id.clone(), row);
            }
        }
    }
    latest
}

fn qualifies_alias(value: &str, canonical: &str, generation: &str, scopes: &[AliasScope], minimum: f64) -> bool {
    scopes.iter().any(|row| {
        row.alias == value
            && row.canonical == canonical
            && row.valid_generations.iter().any(|item| item == generation)
            && row.confidence >= minimum
    })
}

fn normalize_principal(row: &EventRow, aliases: &AliasBook, scopes: &AliasScopes) -> String {
    match aliases.principal_aliases.get(&row.principal) {
        Some(canonical)
            if qualifies_alias(
                &row.principal,
                canonical,
                &row.generation,
                &scopes.principal_scopes,
                scopes.minimum_confidence,
            ) =>
        {
            canonical.clone()
        }
        Some(_) | None => row.principal.clone(),
    }
}

fn normalize_claim(row: &EventRow, aliases: &AliasBook, scopes: &AliasScopes) -> String {
    match aliases.claim_aliases.get(&row.claim) {
        Some(canonical)
            if qualifies_alias(
                &row.claim,
                canonical,
                &row.generation,
                &scopes.claim_scopes,
                scopes.minimum_confidence,
            ) =>
        {
            canonical.clone()
        }
        Some(_) | None => row.claim.clone(),
    }
}

fn select_checkpoints<'a>(
    checkpoint: &'a Checkpoint,
    set_book: &SetBook,
) -> BTreeMap<String, &'a CheckpointRow> {
    let mut selected: BTreeMap<String, &'a CheckpointRow> = BTreeMap::new();
    for row in &checkpoint.rows {
        if row.branch != set_book.checkpoint_branch {
            continue;
        }
        if !row.closed || row.closed_seq > set_book.checkpoint_seq {
            continue;
        }
        match selected.get(&row.id) {
            Some(prior) if prior.closed_seq >= row.closed_seq => {}
            _ => {
                selected.insert(row.id.clone(), row);
            }
        }
    }
    selected
}

fn base_policy(principal: &str, claim: &str, rules: &RulePack, overrides: &AuthorityOverrides) -> AuthorityState {
    match rules
        .rows
        .iter()
        .find(|item| item.principal == principal && item.claim == claim)
    {
        Some(item) => AuthorityState {
            authority_source: item.authority_source.clone(),
            decision: item.decision.clone(),
            freshness: item.freshness.clone(),
            support: item.support.clone(),
        },
        None => overrides.default_if_unmatched.clone(),
    }
}

fn final_policy(
    principal: &str,
    claim: &str,
    row: &EventRow,
    rules: &RulePack,
    overrides: &AuthorityOverrides,
) -> AuthorityState {
    let mut policy = base_policy(principal, claim, rules, overrides);
    for gate in &overrides.consent_gates {
        if gate.principal == principal
            && gate.claim == claim
            && row.consent_state != gate.required_state
        {
            policy = gate.when_not_met.clone();
        }
    }
    for window in &overrides.expiry_windows {
        if window.principal == principal
            && window.claim == claim
            && row.observed_at.as_str() > window.stale_after.as_str()
        {
            policy = window.when_expired.clone();
        }
    }
    policy
}

pub fn fold_a(
    x0: &FrameSet,
    x1: &RulePack,
    x2: &SetBook,
    x3: &AliasBook,
    x4: &AliasScopes,
    x5: &Checkpoint,
    x6: &ReplayManifest,
    x7: &AuthorityOverrides,
) -> Vec<NodeMark> {
    let latest = select_latest(x0, x6);
    let checkpoints = select_checkpoints(x5, x2);
    let mut out = Vec::new();
    for row in latest.values() {
        let principal = normalize_principal(row, x3, x4);
        let claim = normalize_claim(row, x3, x4);
        let policy = final_policy(&principal, &claim, row, x1, x7);
        let prior = checkpoints.get(&row.id);
        let prior_evidence = prior
            .map(|item| item.evidence_id.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let checkpoint_revision = prior
            .map(|item| item.revision.clone())
            .unwrap_or_else(|| x5.name.clone());
        let prior_decision = prior
            .map(|item| item.decision.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let prior_freshness = prior
            .map(|item| item.freshness.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let prior_support = prior
            .map(|item| item.support.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let changed = prior_evidence.as_str() != row.evidence_id.as_str()
            || prior_decision.as_str() != policy.decision.as_str()
            || prior_freshness.as_str() != policy.freshness.as_str()
            || prior_support.as_str() != policy.support.as_str();
        out.push(NodeMark {
            id: row.id.clone(),
            principal,
            claim,
            source_principal: row.principal.clone(),
            source_claim: row.claim.clone(),
            bucket: row.bucket.clone(),
            evidence_id: row.evidence_id.clone(),
            observed_at: row.observed_at.clone(),
            replay_seq: row.replay_seq,
            generation: row.generation.clone(),
            authority_source: policy.authority_source,
            freshness: policy.freshness,
            uncertainty_support: policy.support,
            decision: policy.decision,
            checkpoint_revision,
            prior_decision,
            prior_freshness,
            prior_support,
            recovery_action: if changed { "changed" } else { "unchanged" }.to_string(),
        });
    }
    out
}
RS

cat > layer_b/b29.rs <<'RS'
use crate::types::{NodeMark, RunMark, SetBook};
use std::collections::BTreeMap;

pub fn gate_b(x0: &[NodeMark], x1: &SetBook) -> Vec<RunMark> {
    let by_id: BTreeMap<&str, &NodeMark> = x0.iter().map(|item| (item.id.as_str(), item)).collect();
    let mut out = Vec::new();
    for id in &x1.review {
        if let Some(item) = by_id.get(id.as_str()) {
            out.push(RunMark {
                id: item.id.clone(),
                principal: item.principal.clone(),
                claim: item.claim.clone(),
                source_principal: item.source_principal.clone(),
                source_claim: item.source_claim.clone(),
                bucket: item.bucket.clone(),
                evidence_id: item.evidence_id.clone(),
                observed_at: item.observed_at.clone(),
                replay_seq: item.replay_seq,
                generation: item.generation.clone(),
                authority_source: item.authority_source.clone(),
                freshness: item.freshness.clone(),
                uncertainty_support: item.uncertainty_support.clone(),
                decision: item.decision.clone(),
                checkpoint_revision: item.checkpoint_revision.clone(),
                prior_decision: item.prior_decision.clone(),
                prior_freshness: item.prior_freshness.clone(),
                prior_support: item.prior_support.clone(),
                recovery_action: item.recovery_action.clone(),
            });
        }
    }
    out
}
RS

cat > layer_c/d43.rs <<'RS'
use crate::types::{FieldLine, LedgerRow, RunMark};

fn is_affected(x0: &RunMark) -> bool {
    x0.uncertainty_support == "unsupported" || x0.freshness != "fresh" || x0.decision == "deny"
}

pub fn join_d(x0: &RunMark, x1: &LedgerRow) -> FieldLine {
    let phrase = if is_affected(x0) {
        format!(
            "unsupported ETA certainty: {} links {} to {}; {} authority has freshness {} in {} after {} recovery",
            x1.label,
            x0.id,
            x0.evidence_id,
            x0.principal,
            x0.freshness,
            x0.generation,
            x0.recovery_action
        )
    } else {
        format!(
            "supported uncertainty: {} links {} to {}; fresh {} authority is reviewed in {} after {} recovery",
            x1.label,
            x0.id,
            x0.evidence_id,
            x0.principal,
            x0.generation,
            x0.recovery_action
        )
    };
    FieldLine {
        claim_id: x1.label.clone(),
        record_id: x0.id.clone(),
        evidence_id: x0.evidence_id.clone(),
        principal: x0.principal.clone(),
        support: x0.uncertainty_support.clone(),
        freshness: x0.freshness.clone(),
        generation: x0.generation.clone(),
        recovery_action: x0.recovery_action.clone(),
        phrase,
    }
}
RS

cat > layer_c/c31.rs <<'RS'
use crate::d43::join_d;
use crate::types::{HoldoutSummary, OutputDoc, PackView, RunEntry, RunMark, TransitionEntry};
use std::collections::BTreeMap;

fn is_affected(item: &RunMark) -> bool {
    item.uncertainty_support == "unsupported" || item.freshness != "fresh" || item.decision == "deny"
}

pub fn render_c(x0: &[RunMark], x1: &PackView) -> OutputDoc {
    let mut lines = Vec::new();
    for item in x0 {
        if let Some(row) = x1.ledger.iter().find(|row| row.id == item.id) {
            lines.push(join_d(item, row));
        }
    }
    let mut affected: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for item in x0 {
        if is_affected(item) {
            affected
                .entry(item.principal.clone())
                .or_default()
                .push(item.id.clone());
        }
    }
    let transitions = affected
        .into_iter()
        .map(|(principal, affected_records)| TransitionEntry {
            principal,
            before: "closed-checkpoint".to_string(),
            after: x1.run_id.clone(),
            affected_records,
        })
        .collect();
    OutputDoc {
        runs: vec![RunEntry {
            tool: "eta-risk-provenance".to_string(),
            revision: x1.run_id.clone(),
            record_count: x0.len(),
        }],
        records: x0.to_vec(),
        principal_transitions: transitions,
        holdout_summary: HoldoutSummary {
            pinned_split: x1.pinned.clone(),
            review_count: x1.review_order.len(),
            held_out_count: x1.held_out.len(),
            held_out_records: x1.held_out.clone(),
        },
        statement_evidence: lines,
    }
}
RS

cat > layer_c/p34.rs <<'RS'
use crate::types::{FieldLine, OutputDoc};

fn is_supported(line: &FieldLine) -> bool {
    line.support == "supported" && line.freshness == "fresh"
}

fn push_line(text: &mut String, line: &FieldLine) {
    text.push_str(&format!(
        "- {}; claim {}; record {}; evidence {}; principal {}; freshness {}; generation {}; recovery_action {}; support {}.\n",
        line.phrase,
        line.claim_id,
        line.record_id,
        line.evidence_id,
        line.principal,
        line.freshness,
        line.generation,
        line.recovery_action,
        line.support
    ));
}

pub fn markdown_from_doc(doc: &OutputDoc) -> String {
    let mut text = String::new();
    text.push_str("# Residual risk statement\n\n");
    text.push_str("## Supported uncertainty\n");
    for line in doc.statement_evidence.iter().filter(|line| is_supported(line)) {
        push_line(&mut text, line);
    }
    text.push_str("\n## Unsupported ETA certainty\n");
    text.push_str("The packet does not support precise ETA certainty across the evaluated principals.\n");
    for line in doc.statement_evidence.iter().filter(|line| !is_supported(line)) {
        push_line(&mut text, line);
    }
    text
}

pub fn compact_count(doc: &OutputDoc) -> usize {
    doc.records.len() + doc.statement_evidence.len()
}
RS
