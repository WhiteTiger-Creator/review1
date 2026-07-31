# Probe notes

Workspace crate skew_core exposes bind, fill, gate, and score helpers used by tools/skew_probe.

Rebuild via scripts/refresh_join.sh. The binary lands at tools/skew_probe/skew_probe.

Catalog file cfgs/join_policy.toml lists schema_revs, forbid_drop, and seed.

Local checks write under /app/output/local_chk. Full suite validation uses --suite full with the journal at --journal-out.
