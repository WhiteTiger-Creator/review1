# Audit command contract

Binary `nugetfix`. `nugetfix --version` prints exactly `nugetfix 1.59.0`.
`nugetfix audit` flags:
`--lane --edges --artifacts --packages --cache --pins --feedtags --advisories --xor --bans --peers --retention-hops --out`

Output keys are **exactly** `lane`, `retention_hops`, `artifacts`, `totals` —
do **not** emit `format_version` or any other top-level key.
artifacts sorted by coordinate; each: coordinate, status, holds, risk_score.
status release iff holds empty else hold. Soft edges never cascade.
Holds arrays are lexicographically sorted plain strings (dedupe by string, max risk).
artifact `risk_score` is the sum of deduped hold risks (required integer field).

## Graph topology (repair `/app/data/graphs` before release)

Starter `/app/config/release_matrix.csv` says `edge,2` — repair to **edge,32**
before packaging. Gate starter says `gate,2` — repair to **gate,3**.

- **edge** (`retention_hops=32`): hard spine **must begin** at the first hard edge row
  `svc:app`→`mid:bridge` (never mid-to-mid as the first hop), then
  `mid:bridge`→`mid:spur`→`mid:beam`→`mid:relay`→`mid:span`→`mid:stem`→
  `mid:ridge`→`mid:ford`→`mid:ledge`→`mid:shelf`→`mid:crest`→`mid:cairn`→`mid:peak`→
  `mid:saddle`→`mid:knoll`→`mid:col`→`mid:glen`→`mid:mesa`→`mid:keel`→`mid:tor`→
  `mid:crag`→`mid:rift`→`mid:dune`→`mid:heath`→`mid:scar`→`mid:mere`→`mid:holt`→
  `mid:vale`→`mid:apex`, then interleaved five-arm fan
  from mid:apex `mid:via` / `mid:fork` / `mid:wing` / `mid:yoke` / `mid:arch` into
  `mid:link`→`pkg:blocked` / `pkg:legacy-nuget` / `pkg:quarantine` / `pkg:tainted`.
  Soft decoys (never cascade), emitted **after** all arm→link rows and **before**
  `mid:link` residual children:
  `mid:apex`→`mid:via`, `mid:mesa`→`mid:tor`, `mid:crest`→`mid:peak`,
  `mid:ridge`→`mid:ledge`, `mid:saddle`→`mid:knoll`, `mid:col`→`mid:mesa`,
  `mid:scar`→`mid:vale`, `mid:spur`→`mid:fen`, `mid:holt`→`mid:vale`.
  Include artifact row `mid:fen` (after `mid:spur`). Soft traces (never cascade):
  `svc:app`→`trace:soft`→`pkg:ledger-core`, `svc:app`→`trace:haze`→`pkg:ledger-utils`,
  `svc:app`→`trace:mist`→`pkg:ledger-gateway`, `svc:app`→`trace:fog`→`pkg:ledger-metrics`.
  Primaries hang from `svc:app`. Mid-hop artifact rows precede direct primary rows;
  residuals use order `legacy-nuget`→`tainted`→`blocked`→`quarantine`; then
  `trace:soft`, `trace:haze`, `trace:mist`, `trace:fog`. Fan CSV rows are interleaved per arm in
  via→fork→wing→yoke→arch order. All three banned link children cascade their own
  `ban:` hold. Edge packagerefdrift on `pkg:ledger-gateway`→`ledger-extra` cascades onto the lex spine.
- **core** (`retention_hops=1`): `api:core` → primaries.
- **gate** (`retention_hops=3`): `gw:edge`→`mid:g1`→`mid:g2`→`pkg:alt-a` / `pkg:alt-b`;
  primaries hang from `gw:edge`. `mid:g1` and `mid:g2` artifact rows precede primaries.
  Keep the edge `unused`/`ledger-utils` xor row.

## Holds / risk (dedupe max)

1. Platform tag: feedtags.csv expected_tag for package name != package platform_tag:
   `feedtag:<coord>:<expected>:<actual>` risk 42 (**local only — do not cascade**)
2. Hash drift: pins.csv digest for package name != package digest:
   `hashdrift:<coord>:<expected>:<actual>` risk 43 (**local only — do not cascade**)
3. Cache miss: package digest not listed in cache index digest column:
   `cachemiss:<coord>:<digest>` risk 40 (**local only — do not cascade**)
4. XOR: xor.csv lane,group,package_name; ≥2 names from group present:
   join present names after lexicographic sort with `|`:
   `xor:<group>:<n1>|<n2>` risk 52 on **every** present package coordinate in the group
   (cascade-eligible). Direct holds are **not** collapsed to one member — both
   `pkg:alt-a` and `pkg:alt-b` must carry the same `xor:mgr-choice:alt-a|alt-b` string.
5. Advisory: advisories.csv coordinate,cve -> `advisory:<coord>:<cve>` risk 49 (soft, never cascade)
6. Ban: `ban:<coord>` risk 55 (cascade-eligible)
7. Peer drift: peers.csv lane,coordinate,peer_name; if peer_name is not among package
   `name` values for packages present in the lane artifact set:
   `packagerefdrift:<coord>:<peer_name>` risk 41 (cascade-eligible)

## Cascade propagation (ban / xor / packagerefdrift only)

Cascade **only** `ban:`, `xor:`, and `packagerefdrift:` origins. Never cascade
`feedtag:` / `hashdrift:` / `cachemiss:` / `advisory:`.

Climb the **lex-smallest-parent spine** (not BFS over all parents) within
`retention_hops`. At each reverse step, sort hard parents ascending and climb only
`parents[0]` (diamond: `mid:arch` before `mid:fork`/`mid:via`/`mid:wing`/`mid:yoke`;
then climb `mid:arch`→`mid:apex`→`mid:vale`→`mid:holt`→`mid:mere`→`mid:scar`→…).
Cascades never land on via/fork/wing/yoke.

### Cascade string format (normative)

Emit exactly:

```
cascade:<origin_coordinate>:<underlying_hold_string>
```

Examples:

- Correct: `cascade:pkg:blocked:ban:pkg:blocked`
- Correct: `cascade:pkg:alt-a:xor:mgr-choice:alt-a|alt-b`
- Correct: `cascade:pkg:ledger-gateway:packagerefdrift:pkg:ledger-gateway:ledger-extra`
- Wrong: `cascade:ban:pkg:blocked` (missing origin coordinate)

Risk equals the origin hold risk.

### Lex-smallest-origin collapse (cascades only)

When the **same underlying hold string** would cascade from multiple origins onto
one ancestor, keep only the cascade from the **lexicographically smallest** origin
coordinate. Example: gate xor is present on both `pkg:alt-a` and `pkg:alt-b`;
ancestors receive `cascade:pkg:alt-a:xor:mgr-choice:alt-a|alt-b` only — never
`cascade:pkg:alt-b:xor:...`. Distinct ban strings from `pkg:tainted`,
`pkg:blocked`, and `pkg:quarantine` all propagate onto shared ancestors because
their underlying hold strings differ.

Totals: release,hold,feedtags,hashdrifts,cachemisses,xors,advisories,bans,packagerefdrifts,cascades,risk_score_total.
Count hold-string prefixes (not cascades) for each named counter.

CSV schemas and exact edge-lane row order: see data-dictionary.md.
