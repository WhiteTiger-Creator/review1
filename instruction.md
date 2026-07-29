On this host, cgroup memory.peak accounting for named slice lanes is driven by the systemd oneshot unit `/app/environment/systemd/hwm-unit@.service` (`MemoryAccounting=yes`). Per-slice high-water must stay isolated across lane reset and systemd-style service reload. The live ops report at `/app/output/peak_report.json` is out of policy for the cgroup memcg service path.

Observed ops failures (the interim file `/app/environment/fixtures/q9/haze.json` can look locally fine):

1. Reported memory.peak values disagree with journal-plus-membership recomputation for the same residency samples.
2. Some path_mode rows disagree for the same cgroup slice on recover.
3. A slice reload handoff leaves sticky prior-lane high-water on the next slice.
4. Holdout slices and the wide budget arm break invariants required under the same memcg attribution rules.

`/app/environment/docs/pact_n4.md` is the authoritative normative specification for the graded report schema, path_mode coverage, budget arms, membership maps (including `/app/environment/fixtures/members/map_a.json` and `/app/environment/fixtures/members/map_b.json`), journal kind strings, roster patch timing, fence/reload isolation, checkpoint-hint vs journal-reconstruct authority, and reconstruct invariants. Operator tooling is in `/app/environment/docs/operators.md`, including `/app/environment/scripts/prep_run.sh`, `/app/environment/scripts/drive_matrix.sh` (with `--wide`), and `/app/environment/migrations/mig9.sh`. Live journal and checkpoint bytes land under `/app/output/scratch/` (including `/app/output/scratch/hwm.jnl` and `/app/output/scratch/hwm.ckpt`). Restore correct cgroup memory.peak accounting under `/app/environment` so the normal systemd unit path regenerates `/app/output/peak_report.json`. Static or hand-written JSON writes are not enough.
