# Merge notes

Two tile generations may list different checksums for the same module version. Lower generation wins. Equal generation prefers the `--g1` tile. A pin from `--sum` applies only when that checksum appears among the observed tile checksums for the key.

Scrap files are applied in order. `replace` and `dropreplace` accumulate across scraps; later directives can undo earlier ones. Independent require lines are order-insensitive for input identity. Whitespace and comment-only edits do not change plan identity.

Edge checksums stay keyed to the original module path and version even when a replace target is present; the edge `sum` is not the replace-target module's checksum. For example, a replace of `example.com/lib/legacy` keeps the original-module checksum and that value differs from the `example.com/lib/legacy/v2` `v2.0.0` checksum. Replace edges use class `prop`. When nest files are materialized, `/app/environment/nest/go.sum` must include one line per plan-edge checksum in the usual Go sumdb form `module_path version sum`, using those same original-module checksums (including for locally replaced modules such as `example.com/lib/legacy`).
