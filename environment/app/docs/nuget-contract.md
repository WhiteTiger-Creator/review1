# dotnet nuget packages.lock offline contract

Primary packages **ledger-core**, **ledger-utils**, **ledger-gateway**, and **ledger-metrics** must have
matching digests and platform tags in:

1. `/app/packages.lock.json` and `/app/src/Ledger/packages.lock.json` (NuGet lock JSON)
2. `/app/config/packages.csv`
3. `/app/nuget-cache/index.csv`
4. On-disk wheel filenames under `/app/nuget-cache/` (basename must match `packages.csv` `wheel`)

## Directory.Packages.props + lock package IDs (PascalCase)

`/app/src/Ledger/Directory.Packages.props` must be MSBuild XML with PackageVersion rows:

```xml
<PackageVersion Include="Ledger.Core" Version="1.2.0" />
<PackageVersion Include="Ledger.Utils" Version="1.2.0" />
<PackageVersion Include="Ledger.Gateway" Version="1.2.0" />
<PackageVersion Include="Ledger.Metrics" Version="1.2.0" />
```

NuGet lock JSON package keys must be the same PascalCase IDs (`"Ledger.Core"`, …) with
`contentHash` equal to the matching `index.csv` digest. Do **not** use kebab-case
`ledger-core` as lock keys or PackageVersion `Include=` values (CSV/coordinate names
stay kebab-case `ledger-*` / `pkg:ledger-*`).

## Canonical digests (do NOT recompute)

`/app/nuget-cache/index.csv` digests are the **authoritative offline registry values**. They are
stable placeholder strings (for example `sha256:corecorecoreco…`), **not** byte hashes of
the on-disk `.whl` files.

When repairing:

- **Propagate** the `digest` column from `index.csv` into `packages.lock.json` (`contentHash`)
  and `/app/config/packages.csv` for each primary **and** residual packages listed in the
  index (including `blocked` / `quarantine`).
- Set `platform_tag` / wheel basename to `nupkg` for primaries.
- **Do not** replace those digests with `sha256sum` / `hashlib` of wheel bytes — the
  verifier expects the index.csv placeholders verbatim.
- Do not change package versions. Keep `/app/constraints.txt`.

Empty `/app/legacy-nuget-notes.txt` to exactly: `# emptied for nuget`

## packages.csv size_bytes (required after repair)

| lane | coordinate | size_bytes |
|------|------------|------------|
| edge | pkg:ledger-core | 5000 |
| edge | pkg:ledger-utils | 4000 |
| edge | pkg:ledger-gateway | 5000 |
| edge | pkg:ledger-metrics | **3000** |
| edge | pkg:legacy-nuget | 200 |
| edge | pkg:tainted | 100 |
| edge | pkg:blocked | 100 |
| edge | pkg:quarantine | 100 |
| core | pkg:ledger-core | **9000** |
| core | pkg:ledger-utils | 4000 |
| core | pkg:ledger-gateway | 5000 |
| core | pkg:ledger-metrics | **3000** |
| gate | pkg:ledger-core | 5000 |
| gate | pkg:ledger-utils | 4000 |
| gate | pkg:ledger-gateway | 5000 |
| gate | pkg:ledger-metrics | 3000 |
| gate | pkg:alt-a | 2000 |
| gate | pkg:alt-b | 2000 |

## nuget-report.json

Release emits `/app/dist/nuget-report.json` with:

- `format_version` exactly JSON number `1`
- `package_count` exactly `4`
- `offline_ci` JSON boolean `true`
- `legacy_cleared` JSON boolean — **re-derive on every `release.sh` run** by reading
  `/app/legacy-nuget-notes.txt` at report-emit time. Never hardcode `true`.
  Set `true` only when `notes.strip() == "# emptied for nuget"`; otherwise `false`.
  Verifiers may corrupt the notes file and re-run release; the report flag must flip.
- `nuget_dir` exactly `/app/nuget-cache`
- `platform_tag` exactly `nupkg`

`/app/dist/ledger-check.txt`: one `restore-ok:<name>` per line in order
`ledger-core`, `ledger-utils`, `ledger-gateway`, `ledger-metrics`.

`/app/dist/ledger` must be a file containing exactly `publish-ready` plus one trailing newline.

`/app/dist/nuget-guard.txt` must be exactly:

```
fixtures/bad-lock: hash fail-closed
expected: packages.lock.json hash mismatch against nuget-cache
expected: leave fixtures/bad-lock unrepaired
```

## Intentional residuals — do NOT clear

1. Edge bans `pkg:tainted`, `pkg:blocked`, and `pkg:quarantine`, plus advisory on
   `pkg:legacy-nuget`.
2. Edge packagerefdrift: `pkg:ledger-gateway` missing peer `ledger-extra` (see peers.csv).
3. Gate xor `mgr-choice` between `alt-a` and `alt-b` (both present).
4. Edge xor row `unused` / `ledger-utils` in `xor.csv` (single-member group — keep the row).
5. Leave `fixtures/bad-lock` unrepaired.
