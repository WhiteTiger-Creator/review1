Security operations staff auditing a Unix-domain peer gateway report authorization drift across a three-cycle principal shift on a shared socket path. Regenerated exports from the replay pipeline disagree with pinned audit samples on bind cookies, mask words, journal row counts, child epoch ordering, and resume stability.

Restore correct peer-credential authorization authority under `/app/environment` so the replay pipeline regenerates honest exports. Static files under `/app/output` alone are insufficient — the verifier deletes `/app/output` and regenerates artifacts by running `bash /app/environment/scripts/repro_shift_cycle.sh` with the environment variables that script declares (three shift cycles). Rebuild `/app/bin/gated` and `/app/bin/inspect` after source changes per `/app/environment/docs/toolchain.md`.

## Authorization outputs

The pipeline writes binding_transcript to `/app/output/binding_transcript.json`, principal auth_trace to `/app/output/auth_trace.json`, dual-view probe_report lines to `/app/output/probe_report.jsonl`, auth_journal events to `/app/output/auth_journal.jsonl`, and converge_report to `/app/output/converge_report.json`.

Auth_trace rows carry mark_digest_hex with seal_hex, publish supp_mask for the active policy_epoch, and record bind_cookie. Probe lines expose cred_gap beside seal_match and bind_cookie. Auth_journal records intake and at most one rebind per multi-cycle export. Converge_report includes scope_agreement_count.

Digest material for bind cookies (including attach policy_epoch in cookie minting), attach versus child vault lookup keys, lane fingerprints, rematerialization witness rules (including that inode generation starts at 1 and advances by exactly 1 per rematerialization without rewind), hot-transition drop clearing, facet republish on mask-only changes, attach-epoch child ordering, journal once-semantics with seal-gated rebind, and resume behavior, are in `/app/environment/docs/peer_model.md` and `/app/environment/docs/export_contract.md`.

## Context

Marks `kairo` and `vexa`, drop_mask, and supplemental masks live in `/app/environment/config/principals.toml`. Socket refs `alpha-sock` and `beta-child` both use `/app/environment/state/run.sock` via `/app/environment/config/endpoints.toml`.

If `/app/output/binding_transcript.json` already contains rows, re-invoking gated must leave all five exports unchanged per the resume rules in `/app/environment/docs/peer_model.md`.
