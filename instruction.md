The NFS export ACL reconciliation daemon at `/app/bin/nfs-acld` manages NFS export paths, per-client grants, squash and anon mapping, secure-port sticky flags, and waitlist promotion for storage operators. The systemd oneshot `/app/systemd/nfs-export-acld.service` must reload `/app/var/lib/nfs-acld/export.journal` and converge runtime inventory so grants, waitlist state, and compliance metrics comply with `/app/docs/nfs-export-ops-policy.md`. Configure the service with `/app/config/exports.json`.

After convergence, `/app/run/export_acls.json` and `/app/run/export_metrics.json` must satisfy the ops policy schemas, ordering rules, and metric formulas. Do not modify `/app/config/`, `/app/docs/`, `/app/governance/`, `/app/systemd/`, or `/app/var/`.

Note that code comments and docstrings may themselves contain errors.
