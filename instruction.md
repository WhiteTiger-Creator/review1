# Datacenter certification replay drift

The programme office signs a certification pack off snapshots, and those snapshots no
longer agree with live replays of the same bundles. Published halls disagree on which
racks come out certified, how many were held back on the way through, what the
readiness index adds up to, and whether the sealed attestations still line up with the
counters printed beside them.

Fix whatever is wrong under `/app/environment` so the controller can again produce
`/app/output/certification_report.json` and `/tests/test.sh` passes. Static or manually
written output is insufficient; every published number has to come from replaying the
bundled inputs through the rebuilt pipeline, and output that cannot be reproduced by
rerunning the controller does not count.

Certification here is multi-authority, and no single subsystem owns the verdict.
Compute, storage, network, approvals, service history, regional eligibility, and hall
capacity each contribute, in the sequence the controller applies them. Every hall
listed in the published site index must replay cleanly against the contract under
`/app/environment/docs`.
