# Release packaging contract

`/app/scripts/release.sh` must:

1. **Fail-closed preflight** (abort non-zero **before** deleting `/app/dist`) when any of:
   - `release_matrix.csv` is not edge=32 / core=1 / gate=3
   - first hard edge row is not `svc:app,mid:bridge`
   - soft `mid:spur,mid:fen` or soft **`mid:holt,mid:vale`** decoy missing, or soft
     decoys appear after `mid:link` residual children
   - fan is not interleaved per arm, gate alts are not siblings under `mid:g2`,
     artifacts missing `edge,mid:link` / `edge,mid:fen`
   - workspace Cargo version is not `1.59.0`, or `.cargo/config.toml` lacks `offline = true`
   - `nuget.config` is not local-feed-only (`/app/nuget-cache`), or Directory.Packages.props
     PackageVersion rows are not PascalCase `Ledger.*` at Version `1.2.0`
   Every abort message MUST contain the literal lowercase substring `fail-closed`
   (not only a custom token such as `release preflight fail`).
2. Delete and recreate `/app/dist` only after preflight passes (the only directory
   allowed directly under `/app/dist` is `bundles/` plus file artifacts). Unpacked lane
   trees live only under `bundles/`.
3. Create `/app/.release-tmp/packaging.ok` with exactly `ok\n` and keep packaging temps
   under `/app/.release-tmp` (`TMPDIR`/`TMP`/`TEMP`).
4. Emit `/app/dist/nuget-report.json`, `/app/dist/nuget-guard.txt`, `/app/dist/ledger-check.txt`,
   and `/app/dist/ledger` (`publish-ready\n`) **before** packaging lanes.
   `legacy_cleared` must be re-derived by reading `/app/legacy-nuget-notes.txt` on **this**
   run — never hardcode `true`.
5. Build **once** with `cargo build --release --locked --offline -p nugetfix-cli` before
   any lane (`CARGO_NET_OFFLINE=true`).
6. For each row in `/app/config/release_matrix.csv` (`lane,retention_hops`) in CSV row order:
   - Unpacked bundle root: `/app/dist/bundles/nugetfix-<lane>/`
   - Archive: `/app/dist/nugetfix-<lane>-linux-x86_64.tar.gz` with tar member root
     `nugetfix-<lane>/...`
   - Deterministic packing: `SOURCE_DATE_EPOCH=1700000000`, tar `--mtime=@1700000000`,
     uid/gid 0, `gzip -n`.
7. Sequencing: finish that lane's `share/audit-preview.json` → seal that lane's tar.gz →
   record digests. Write `/app/dist/release-manifest.json` only after every lane archive
   exists. Write `checksums.sha256` last.
8. Manifest `bundles` array order MUST match `release_matrix.csv` row order.

## Bundle layout (required paths)

```
nugetfix-<lane>/
  bin/nugetfix
  LICENSES.txt
  VERSION                       # exactly: 1.59.0\n
  share/lane-policy.json        # {"lane":"<lane>","retention_hops":N}
  share/edges.csv               # lane-filtered from data/graphs/edges.csv (col 0 = lane)
  share/artifacts.csv           # lane-filtered from data/graphs/artifacts.csv
  share/packages.csv            # lane-filtered from config/packages.csv
  share/xor.csv                 # lane-filtered from config/xor.csv
  share/peers.csv               # lane-filtered from config/peers.csv
  share/feedtags.csv            # full copy of config/feedtags.csv
  share/cache-index.csv         # full copy of nuget-cache/index.csv
  share/pins.csv                # full copy of config/pins.csv
  share/advisories.csv          # full copy of config/advisories.csv
  share/bans.csv                # full copy of config/bans.csv
  share/run-smoke.sh            # POSIX #!/bin/sh; invokes bin/nugetfix audit ... --cache --feedtags --peers --out <path>
  share/audit-preview.json      # MUST live under share/, written by run-smoke.sh
```

Lane-filtered CSVs MUST keep the source header and include every row whose first column
equals the lane (and no other lanes). If a lane has zero matching rows, keep the header
alone. Do not hand-write golden `audit-preview.json`.
`run-smoke.sh` MUST be `#!/bin/sh` (no bash/`pipefail`), MUST pass `--cache`,
`--feedtags`, and `--peers` to audit, MUST accept outfile paths containing spaces, and
MUST contain this exact optional-out expansion (variable name `$HERE` — do not substitute
`$ROOT` / `$ROOTDIR` / an `if [ -z "$1" ]` rewrite):

```sh
OUT=${1:-"$HERE/share/audit-preview.json"}
```

With no `$1`, rewrite `share/audit-preview.json`. With `$1`, write that path (including
paths with spaces).

## `/app/dist/release-manifest.json` schema

```json
{
  "format_version": 1,
  "package": {
    "name": "nugetfix-cli",
    "version": "1.59.0",
    "target": "x86_64-unknown-linux-gnu"
  },
  "workspace": [
    {
      "name": "<crate name from crates/*/Cargo.toml [package].name — nugetfix-cli not binary nugetfix>",
      "version": "<resolved version string>",
      "license": "<resolved license string>",
      "dependencies": ["<dep crate names sorted ascending>"]
    }
  ],
  "hash": { "...same object as /app/dist/nuget-report.json..." },
  "bundles": [
    {
      "lane": "<lane>",
      "archive": "nugetfix-<lane>-linux-x86_64.tar.gz",
      "archive_sha256": "<sha256 of sealed archive>",
      "binary_sha256": "<sha256 of bundle bin/nugetfix>",
      "policy_sha256": "<sha256 of share/lane-policy.json>",
      "audit_preview_sha256": "<sha256 of share/audit-preview.json>",
      "artifact_count": 0,
      "hold_count": 0,
      "risk_score_total": 0
    }
  ]
}
```

Notes:

- `package` is a **nested object** with `name`, `version`, and `target` — never a bare string.
- `package.name` and each `workspace[].name` must be the Cargo **`[package].name`**
  (`nugetfix-cli` for the CLI crate). Do **not** substitute the on-disk binary basename
  `nugetfix` from `[[bin]]` / `bin/nugetfix`.
- Field name is `workspace` (not `workspace_crates`). List of objects with exactly `name`,
  `version`, `license`, `dependencies`.
- **`workspace` order:** ascending by crate directory path under `crates/*/Cargo.toml`
  (`nugetfix-cli`, `nugetfix-core`, `nugetfix-graph`).
- **`bundles` order:** exactly the row order of `/app/config/release_matrix.csv`
  (currently `edge`, then `core`, then `gate`). Do not sort by lane name.
- Digest keys must be named `archive_sha256`, `binary_sha256`, `policy_sha256`, and
  `audit_preview_sha256`.
- `artifact_count` equals `len(audit-preview.artifacts)`; `hold_count` equals
  `audit-preview.totals.hold`; `risk_score_total` equals
  `audit-preview.totals.risk_score_total`.
- `hash` must deep-equal `/app/dist/nuget-report.json` (the full object, not a hex digest).

## `/app/dist/checksums.sha256`

- One line per file under `/app/dist` except `checksums.sha256` itself (include `bundles/**`).
- Format: `<sha256>  <path-relative-to-dist>` (two spaces).
- Bare relative paths (**no `./` prefix**), sorted (`LC_ALL=C`).

## Dist root layout

Only the `bundles/` directory is allowed directly under `/app/dist` (plus file artifacts
such as reports, archives, checksums, and the `ledger` marker). Unpacked lane trees must
not sit at the dist root.
Keep `/app/.cargo/config.toml` with `offline = true`.
