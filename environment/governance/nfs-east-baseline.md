# NFS East Governance Baseline

When a site profile overlay is not mounted, regional operators may fall back to the governance baseline for discovery drills:

- `max_clients_per_export = 8`
- `default_squash = no_root_squash`
- `default_anon_uid = 0`
- `default_access = rw`

These values exist for tabletop exercises only. Live oneshot convergence for production export tables follows `/app/docs/nfs-export-ops-policy.md`, which treats base `/app/config/exports.json` as authoritative for max clients, squash defaults, anon mapping, access defaults, secure-port enforcement, table id, evaluation clock, journal path, and output directory.
