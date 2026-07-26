
# Ensemble Release Model-Review Dossier

This dossier is the authoritative governance record for the ensemble release
program. It records how logical run identity, annotation precedence,
calibrated feature provenance, AUC baseline selection, and conflict handling
were decided over successive model-risk review meetings. Where an early
proposal was later replaced, the superseding decision is marked explicitly
with its decision identifier, status, and date. Read the authoritative
sections (2–6) together with the worked examples (section 7); no single
paragraph states the full policy, and no machine-readable answer table is
provided.

## 1. Table of contents

1. Table of contents
2. Logical run identity (authoritative)
3. Annotation precedence (authoritative)
4. Calibrated feature paths (authoritative)
5. AUC baseline selection (authoritative)
6. Conflicts and atomicity (authoritative)
7. Worked examples (non-normative)
8. Review-meeting minutes and postmortems (context)

## 2. Logical run identity (authoritative)

**DEC-2024-03-11 (approved).** Every run in the program is uniquely
identified by its ledger `run_uid`. Release branches assign their own
branch-local node names and alias spellings for operational convenience,
recorded in the ledger as `release_alias` and `legacy_alias`. Reconciliation
MUST resolve a branch-local identifier to a `run_uid` by consulting BOTH the
`release_alias` and `legacy_alias` columns. If a single alias string maps to
two different `run_uid` values, the evidence is ambiguous and the run MUST be
rejected (validation failure, token `AMBIGUOUS_ALIAS`) with no output files.
A reference to a run that exists in neither the ledger's `run_uid` column nor
its alias columns is an `UNKNOWN_RUN` validation failure.

> Superseded: DEC-2023-09-02 (proposal) suggested stripping a fixed branch
> prefix (`RB-`, `LG-`) to derive identity. This is **superseded** by
> DEC-2024-03-11 because prefixes are not stable across branches and cause
> unrelated runs to merge.

## 3. Annotation precedence (authoritative)

**DEC-2024-05-20 (approved).** Each lineage edge may carry one or more
annotation candidates. A candidate has a status (`proposal`, `approved`, or
`superseded`), a decision date, and a content token drawn from
{warmstart, calibration_member, ensemble_member, feature_inheritance,
promotion, quarantine}. The canonical annotation for an edge is resolved as
follows: discard every `superseded` candidate; if any `approved` candidate
remains, the winner is drawn from the approved candidates, otherwise from the
proposals; among the winning status, the candidate with the latest decision
date wins; remaining ties break on content lexical order.

**DEC-2024-08-01 (approved) — legacy compatibility appendix.** The `rc-green`
branch historically stored edge annotations in the Graphviz `xlabel` and
`taillabel` attributes rather than `label`. For the purpose of gathering
annotation candidates, `xlabel` and `taillabel` values count as `label`
content. This is a representation difference, never a semantic conflict.

> Superseded: DEC-2024-02-14 (proposal) applied annotations in encounter
> order (first statement wins). **Superseded** by DEC-2024-05-20.

## 4. Calibrated feature paths (authoritative)

**DEC-2024-06-18 (approved).** The `feature_path` of a node is the chain of
`run_uid`s at which the feature set actually changed, in ancestry order,
joined by `>`. Walking from a parent to a child: if the child's
`stage_kind` is `train` or `ensemble` AND the child's `feature_set_hash`
differs from the parent's, the path extends by appending the child's
`run_uid`; otherwise the child inherits the parent's path unchanged.
Calibration (`calibrate`) and promotion (`promote`) stages NEVER change the
feature set, so they always inherit the parent path. An `ensemble` node is
always feature-changing; when it has multiple parents its path is the
bracketed, lexically-sorted union of parent paths joined by `|`, followed by
`>` and the ensemble's own `run_uid`. A root run's path is its own `run_uid`.

> Superseded: DEC-2023-11-30 (proposal) built the path from raw ancestry
> (every parent/child edge). **Superseded**: it double-counts calibration
> and promotion stages.

## 5. AUC baseline selection (authoritative)

**DEC-2024-07-09 (approved).** The `auc_delta` on an edge parent→child is the
child's AUC minus the AUC of the nearest released ancestor that shares the
child's `evaluation_cohort`. "Nearest" is measured in edges walked upward
starting from the edge's own parent; ties at the same distance break on
`run_uid`. Only ancestors with `release_status = released` and a matching
cohort qualify; if no such ancestor exists, `auc_delta` and `baseline` are
omitted from that edge. The delta is computed with exact decimal arithmetic,
quantized to six fractional digits using banker's rounding (HALF_EVEN), and
emitted as a string with exactly six fractional digits.

> Superseded: DEC-2024-01-22 (proposal) subtracted the immediate parent's
> AUC using double-precision floating point. **Superseded** by DEC-2024-07-09
> because the immediate parent is frequently a non-released calibration run in
> a different cohort, and floating point introduces drift.

## 6. Conflicts and atomicity (authoritative)

**DEC-2024-09-15 (approved).** After alias resolution, the set of logical
parent→child relationships derived from the two worktrees MUST agree. A
disagreement is `CONFLICTING_PARENTAGE`. Node-level metric evidence that
disagrees across worktrees for the same `run_uid` is `CONFLICTING_METRICS`.
Both are fatal (exit 3) and produce no output. Representational differences —
alias spellings and legacy attribute placement — are recorded in
`representation_differences` and never populate `semantic_discrepancies`.

## 7. Worked examples (non-normative, consistent with sections 2–6)

**Example A (feature path through calibration).** Consider `run-01` (train,
fs-a) → `run-02` (train, fs-a) → `run-03` (train, fs-b) → `run-04`
(calibrate, fs-b) → `run-05` (promote, fs-b). `run-02` inherits `run-01`
because it is a training stage whose feature-set hash did not change, so its
path is `run-01`. `run-03` changed the feature set, so its path is
`run-01>run-03`. `run-04` and `run-05` are calibration and promotion, so they
both inherit `run-01>run-03`.

**Example B (baseline crosses a non-released parent).** For the edge
`run-03`→`run-04`, the child `run-04` is in `cohortA`. Its immediate parent
`run-03` is a candidate, so it does not qualify. Walking upward, `run-02`
is released and in `cohortA`, so it is the baseline. The delta is
`run-04.auc − run-02.auc`.

**Example C (no qualifying baseline).** The ensemble `run-09` (cohortA) has a
parent `run-08` in `cohortB`. Walking upward from `run-08` finds only
`cohortB` runs, so the edge `run-08`→`run-09` has no baseline and omits both
`auc_delta` and `baseline`. The other parent edge `run-05`→`run-09` does have
a `cohortA` released ancestor.

**Example D (annotation precedence).** The edge `run-02`→`run-03` carries a
`proposal` of `warmstart` (2024-01-10) and an `approved` `feature_inheritance`
(2025-02-01). The approved candidate wins, so the canonical annotation is
`feature_inheritance`. The edge `run-11`→`run-12` carries a proposal, an
approved `quarantine`, and a superseded `warmstart`; the superseded candidate
is discarded and the approved `quarantine` wins.


## 8. Review-meeting minutes and postmortems (context)

### 8.1 Review meeting 001 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 001 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.2 Review meeting 002 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 002 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.3 Review meeting 003 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 003 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.4 Review meeting 004 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 004 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.5 Review meeting 005 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 005 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.6 Review meeting 006 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 006 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.7 Review meeting 007 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 007 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.8 Review meeting 008 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 008 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.9 Review meeting 009 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 009 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.10 Review meeting 010 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 010 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.11 Review meeting 011 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 011 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.12 Review meeting 012 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 012 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.13 Review meeting 013 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 013 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.14 Review meeting 014 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 014 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.15 Review meeting 015 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 015 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.16 Review meeting 016 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 016 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.17 Review meeting 017 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 017 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.18 Review meeting 018 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 018 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.19 Review meeting 019 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 019 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.20 Review meeting 020 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 020 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.21 Review meeting 021 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 021 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.22 Review meeting 022 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 022 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.23 Review meeting 023 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 023 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.24 Review meeting 024 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 024 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.25 Review meeting 025 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 025 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.26 Review meeting 026 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 026 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.27 Review meeting 027 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 027 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.28 Review meeting 028 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 028 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.29 Review meeting 029 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 029 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.30 Review meeting 030 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 030 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.31 Review meeting 031 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 031 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.32 Review meeting 032 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 032 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.33 Review meeting 033 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 033 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.34 Review meeting 034 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 034 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.35 Review meeting 035 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 035 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.36 Review meeting 036 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 036 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.37 Review meeting 037 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 037 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.38 Review meeting 038 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 038 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.39 Review meeting 039 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 039 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.40 Review meeting 040 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 040 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.41 Review meeting 041 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 041 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.42 Review meeting 042 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 042 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.43 Review meeting 043 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 043 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.44 Review meeting 044 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 044 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.45 Review meeting 045 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 045 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.46 Review meeting 046 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 046 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.47 Review meeting 047 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 047 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.48 Review meeting 048 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 048 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.49 Review meeting 049 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 049 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.50 Review meeting 050 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 050 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.51 Review meeting 051 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 051 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.52 Review meeting 052 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 052 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.53 Review meeting 053 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 053 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.54 Review meeting 054 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 054 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.55 Review meeting 055 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 055 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.56 Review meeting 056 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 056 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.57 Review meeting 057 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 057 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.58 Review meeting 058 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 058 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.59 Review meeting 059 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 059 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.60 Review meeting 060 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 060 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.61 Review meeting 061 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 061 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.62 Review meeting 062 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 062 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.63 Review meeting 063 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 063 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.64 Review meeting 064 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 064 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.65 Review meeting 065 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 065 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.66 Review meeting 066 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 066 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.67 Review meeting 067 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 067 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.68 Review meeting 068 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 068 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.69 Review meeting 069 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 069 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.70 Review meeting 070 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 070 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.71 Review meeting 071 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 071 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.72 Review meeting 072 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 072 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.73 Review meeting 073 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 073 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.74 Review meeting 074 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 074 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.75 Review meeting 075 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 075 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.76 Review meeting 076 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 076 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.77 Review meeting 077 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 077 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.78 Review meeting 078 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 078 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.79 Review meeting 079 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 079 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.80 Review meeting 080 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 080 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.81 Review meeting 081 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 081 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.82 Review meeting 082 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 082 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.83 Review meeting 083 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 083 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.84 Review meeting 084 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 084 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.85 Review meeting 085 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 085 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.86 Review meeting 086 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 086 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.87 Review meeting 087 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 087 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.88 Review meeting 088 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 088 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.89 Review meeting 089 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 089 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.90 Review meeting 090 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 090 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.91 Review meeting 091 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 091 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.92 Review meeting 092 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 092 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.93 Review meeting 093 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 093 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.94 Review meeting 094 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 094 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.95 Review meeting 095 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 095 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.96 Review meeting 096 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 096 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.97 Review meeting 097 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 097 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.98 Review meeting 098 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 098 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.99 Review meeting 099 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 099 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.100 Review meeting 100 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 100 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.101 Review meeting 101 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 101 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.102 Review meeting 102 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 102 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.103 Review meeting 103 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 103 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.104 Review meeting 104 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 104 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.105 Review meeting 105 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 105 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.106 Review meeting 106 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 106 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.107 Review meeting 107 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 107 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.108 Review meeting 108 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 108 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.109 Review meeting 109 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 109 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.110 Review meeting 110 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 110 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.111 Review meeting 111 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 111 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.112 Review meeting 112 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 112 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.113 Review meeting 113 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 113 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.114 Review meeting 114 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 114 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.115 Review meeting 115 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 115 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.116 Review meeting 116 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 116 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.117 Review meeting 117 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 117 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.118 Review meeting 118 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 118 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.119 Review meeting 119 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 119 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.120 Review meeting 120 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 120 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.121 Review meeting 121 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 121 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.122 Review meeting 122 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 122 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.123 Review meeting 123 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 123 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.124 Review meeting 124 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 124 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.125 Review meeting 125 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 125 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.126 Review meeting 126 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 126 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.127 Review meeting 127 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 127 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.128 Review meeting 128 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 128 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.129 Review meeting 129 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 129 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.130 Review meeting 130 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 130 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.131 Review meeting 131 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 131 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.132 Review meeting 132 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 132 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.133 Review meeting 133 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 133 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.134 Review meeting 134 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 134 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.135 Review meeting 135 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 135 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.136 Review meeting 136 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 136 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.137 Review meeting 137 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 137 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.138 Review meeting 138 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 138 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.139 Review meeting 139 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-08,
following its descendants run-11 and run-02, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-08 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-02 is
anchored on the nearest released ancestor sharing run-02's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-08 and run-02 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 139 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.140 Review meeting 140 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-09,
following its descendants run-02 and run-07, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-09 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-07 is
anchored on the nearest released ancestor sharing run-07's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-09 and run-07 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 140 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.141 Review meeting 141 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-10,
following its descendants run-05 and run-12, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-10 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-12 is
anchored on the nearest released ancestor sharing run-12's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-10 and run-12 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 141 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.142 Review meeting 142 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-11,
following its descendants run-08 and run-05, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-11 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-05 is
anchored on the nearest released ancestor sharing run-05's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-11 and run-05 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 142 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.143 Review meeting 143 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-12,
following its descendants run-11 and run-10, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-12 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-10 is
anchored on the nearest released ancestor sharing run-10's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-12 and run-10 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 143 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.144 Review meeting 144 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-01,
following its descendants run-02 and run-03, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-01 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-03 is
anchored on the nearest released ancestor sharing run-03's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-01 and run-03 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 144 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.145 Review meeting 145 — annotation precedence across proposal and approved decisions

The model-risk board reconvened to revisit annotation precedence across proposal and approved decisions. The discussion
reaffirmed DEC-2024-05-20 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-02,
following its descendants run-05 and run-08, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-02 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-08 is
anchored on the nearest released ancestor sharing run-08's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-02 and run-08 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 145 were
folded back into DEC-2024-05-20 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.146 Review meeting 146 — calibrated feature-path construction through calibration stages

The model-risk board reconvened to revisit calibrated feature-path construction through calibration stages. The discussion
reaffirmed DEC-2024-06-18 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-03,
following its descendants run-08 and run-01, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-03 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-01 is
anchored on the nearest released ancestor sharing run-01's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-03 and run-01 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 146 were
folded back into DEC-2024-06-18 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.147 Review meeting 147 — nearest-released AUC baseline selection and decimal precision

The model-risk board reconvened to revisit nearest-released AUC baseline selection and decimal precision. The discussion
reaffirmed DEC-2024-07-09 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-04,
following its descendants run-11 and run-06, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-04 and run-11 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-06 is
anchored on the nearest released ancestor sharing run-06's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-04 and run-06 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 147 were
folded back into DEC-2024-07-09 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.148 Review meeting 148 — legacy Graphviz attribute compatibility for xlabel and taillabel

The model-risk board reconvened to revisit legacy Graphviz attribute compatibility for xlabel and taillabel. The discussion
reaffirmed DEC-2024-08-01 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-05,
following its descendants run-02 and run-11, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-05 and run-02 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-11 is
anchored on the nearest released ancestor sharing run-11's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-05 and run-11 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 148 were
folded back into DEC-2024-08-01 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.149 Review meeting 149 — conflicting parentage and metric evidence handling

The model-risk board reconvened to revisit conflicting parentage and metric evidence handling. The discussion
reaffirmed DEC-2024-09-15 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-06,
following its descendants run-05 and run-04, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-06 and run-05 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-04 is
anchored on the nearest released ancestor sharing run-04's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-06 and run-04 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 149 were
folded back into DEC-2024-09-15 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.

### 8.150 Review meeting 150 — logical run identity and alias resolution

The model-risk board reconvened to revisit logical run identity and alias resolution. The discussion
reaffirmed DEC-2024-03-11 and traced its consequences through the current release
candidates. Reviewers walked the lineage segment anchored on run-07,
following its descendants run-08 and run-09, and confirmed that resolving
every branch-local spelling to the ledger `run_uid` keeps the two release
worktrees in agreement. A recurring failure mode raised in the meeting was
an implementation that keyed identity on branch-local DOT node names; such
an implementation duplicates run-07 and run-08 and then reports spurious
parentage conflicts. The board reiterated that alias spellings and the
placement of an annotation in `label` versus `xlabel`/`taillabel` are
representation differences only.

On metrics, the board reviewed how the delta for an edge into run-09 is
anchored on the nearest released ancestor sharing run-09's evaluation
cohort, not on its immediate parent, and that the subtraction is performed
with exact decimal arithmetic quantized to six fractional digits under
banker's rounding. The minutes note that a calibration or promotion stage
between run-07 and run-09 must not extend the feature path, because neither
stage changes the feature-set hash. Action items from meeting 150 were
folded back into DEC-2024-03-11 without altering its approved intent; no new rule
was introduced, and earlier proposals on this topic remain superseded.
