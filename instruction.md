# TUF Metadata Rollout Verifier

A signed-metadata supply-chain rollout verifier at `/app/` must assess the TUF-style repository under `/app/data/repo/` against `/app/config/trust_policy.json` and `/app/config/rollout_lanes.json`, then write `/app/output/rollout_report.json`. The binary is `/app/bin/tuf-rollout-verifier`; `--help` must print usage and exit successfully without running verification.

Verification semantics, report schema (including config echo, lane gates, freeze evaluation, chain integrity, and the summary digest), and immutability constraints are defined solely by `/app/docs/rollout_contract.md`. Assessments must converge on that contract for the bundled repository. Do not modify the trust policy, lane map, signed metadata, integrity digests, or target payloads. Do not add private signing material under `/app/config/keys`, and do not introduce a repository regenerator at `/app/scripts/gen_repo.py`. Note that code comments and docstrings may themselves contain errors.
