# Offline build mirror contract

`node /app/bin/repair-lock.js` prepares a build plan for the workspace in `/app/workspace` and writes `/app/output/build-plan.json`. It reads only files under `/app/`. The build has no network access.

## Inputs

Authoritative inputs are `/app/workspace/package.json`, `/app/workspace/package-lock.json`, `/app/workspace/packages/*/package.json`, `/app/registry/packages.json`, and `/app/config/policy.json`.

`/app/registry/packages.json` contains a `packages` object. Each package maps version strings to metadata objects that may include `license`, `integrity`, `tarball`, `dependencies`, `optionalDependencies`, `peerDependencies`, `peerDependenciesMeta`, `engines`, `deprecated`, `yanked`, and `os`.

Package names are case sensitive. Version strings use numeric SemVer cores with optional prerelease suffixes after a hyphen.

## Resolution order

Build the dependency graph that would be installed for the root package.

Walk root `dependencies` first, then every dependency required by packages that were selected. Root `devDependencies` are included only when `includeDevDependencies` is true. Root `optionalDependencies` are included only when `includeOptionalDependencies` is true. Workspace package `devDependencies` are never walked.

Within each manifest, walk dependency names in lexicographic order. Process requests in the order they are appended to the request queue.

For each request, determine the real package name. Alias specs use the form `npm:real-name@range` and keep the alias as the output name.

Replace the requested range with `overrides[real]` when an override exists. Overrides replace the range before any version selection.

When no override exists and `resolutions[real]` is present, select that exact version if it satisfies the effective range. If the pin does not satisfy the effective range, record the request in `unresolved` with reason `resolution out of range` and do not select a version.

Workspace specs use the `workspace:` prefix. `workspace:*` accepts the local version. `workspace:^` and `workspace:~` expand against the local version using the caret and tilde rules below. A plain semver range also selects a matching workspace package when the local version satisfies the range. When a workspace spec names a package that is not present in the workspace, record the request in `unresolved` with reason `workspace package missing`. When the workspace package is present but its local version does not satisfy the effective range, record the request in `unresolved` with reason `no compatible version`.

Registry selection chooses the highest compatible version that passes engine, deprecation, yanked, and stability rules described below.

If two compatible ranges that share the same output name can share one version, keep one selected entry. Version sharing and deduplication key on the output name, not the real package name. An alias and a direct dependency on the same real package always produce separate entries, even when they could share a version. If two direct requests for the same real package name cannot share a version, keep separate entries by appending `#2`, `#3`, and so on to later output names in request order. The `package` field always contains the real package name.

Registry packages expose runtime edges from `dependencies`. They expose optional edges from `optionalDependencies` only when `includeOptionalDependencies` is true. Selected workspace packages expose runtime edges from `dependencies` and optional edges from `optionalDependencies` only when `includeOptionalDependencies` is true.

Skip a transitive registry dependency when every published version of that dependency lists an `os` array and none of those arrays contains `buildHost`.

Peer dependencies are not installed automatically. After selection completes, evaluate peers for every selected package. Optional peers declared in `peerDependenciesMeta` with `"optional": true` produce no peer warning. Missing non optional peers use reason `missing peer dependency`. Present peers outside the requested range use reason `peer range mismatch`.

## SemVer

Supported range forms are exact versions, `*`, x ranges such as `1.2.x`, caret ranges, tilde ranges, hyphen ranges, space joined comparator sets, `||` unions, workspace references, and npm alias specs.

Exact versions match only themselves.

Caret `^M.m.p` allows `>=M.m.p` below the caret upper bound. For major zero, the upper bound follows npm zero major rules.

Tilde `~M.m.p` allows patch level increases within the same minor line.

Hyphen ranges `A - B` are inclusive on both ends.

Comparator sets require every comparator to pass. Supported operators are `>=`, `>`, `<=`, `<`, and `=`.

`||` unions succeed when any alternative succeeds.

Prerelease versions are excluded from caret, tilde, hyphen, and comparator matches unless the range operand itself carries the same `major.minor.patch` prefix as the candidate prerelease.

## Version preference

Deprecated versions are never selected. If only deprecated versions satisfy a range, the request becomes unresolved with reason `no compatible version`.

Among non deprecated candidates that satisfy the range and `engines.node`, rank yanked versions below non yanked versions. If every satisfying candidate is yanked, select the highest yanked version.

When `preferStable` is true, non prerelease versions outrank prerelease versions inside the same deprecation and yanked class. Choose the highest version within the winning class.

Engine expressions use `>=`, `<`, and space joined combinations such as `>=18.0.0 <23.0.0`.

## Policy audits

`policy.json` supplies `nodeVersion`, `buildHost`, `includeDevDependencies`, `includeOptionalDependencies`, `preferStable`, `licenseAllowlist`, `blockedPackages`, `overrides`, `resolutions`, `patches`, and `expectedIntegrityHost`.

Packages outside `licenseAllowlist` remain selected and are listed in `policyViolations` with rule `license` and message `license <license> is not allowed`.

Packages in `blockedPackages` are never selected. Blocked requests are listed in `unresolved` with reason `blocked by policy`.

Patch entries apply only when the selected version equals the patch version. Matching entries set `patched` to true and replace `integrity` with the patch integrity from policy.

Selected registry packages whose tarball host differs from `expectedIntegrityHost` are listed in `mirrorWarnings`.

## Lock drift

Read `/app/workspace/package-lock.json`. For each lock entry whose path is exactly `node_modules/<name>` or `node_modules/@scope/name`, compare the locked version to the selected registry package whose output `name` equals that lock name. When the selected package exists and the versions differ, record a drift item. Ignore lock entries with no matching selected package. Ignore workspace packages. `plannedIntegrity` is the selected package integrity after patch substitution.

## Output

Write stable pretty printed JSON with two spaces and no trailing newline.

Top level keys in order: `root`, `nodeVersion`, `packages`, `unresolved`, `peerWarnings`, `policyViolations`, `mirrorWarnings`, `lockDrift`, `summary`.

`packages` is sorted by output name. Each entry contains keys in order: `name`, `package`, `version`, `source`, `requestedBy`, `license`, `integrity`, `tarball`, `patched`, `yanked`.

Workspace entries use null for `integrity` and `tarball`, false for `yanked`, and false for `patched` unless a patch entry matches.

`requestedBy` is a sorted list of unique requestors. Use `root` for the root manifest.

`unresolved` is sorted by `name`, then `requestedBy`, then `range`. Each entry contains `name`, `range`, `requestedBy`, and `reason`. `name` is the dependency name from the requesting manifest. `range` is the manifest specifier before override substitution. `requestedBy` is a single requestor identifier.

`peerWarnings` is sorted by `package`, then `peer`, then `requested`. Each entry contains `package`, `peer`, `requested`, `found`, and `reason`. `found` is null when the peer is not installed, otherwise the selected version string of the peer package.

`policyViolations` is sorted by `package`, then `rule`. Each entry contains `package`, `version`, `rule`, and `message`.

`mirrorWarnings` is sorted by `package`, then ascending semver `version`. Each entry contains `package`, `version`, `tarball`, and `expectedHost`.

`lockDrift` is sorted by `package`. Each entry contains `package`, `lockVersion`, `plannedVersion`, `lockIntegrity`, and `plannedIntegrity`.

`summary` contains `packageCount`, `workspaceCount`, `registryCount`, `patchedCount`, `yankedSelectedCount`, `unresolvedCount`, `peerWarningCount`, `policyViolationCount`, `mirrorWarningCount`, and `lockDriftCount`. Each counter matches its section.
