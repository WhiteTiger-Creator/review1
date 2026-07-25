# Data dictionary

## release_matrix.csv

`lane,retention_hops` — after repair: edge=32, core=1, gate=3.
Starter still says edge=2 / gate=2 — repair before packaging.

## packages.csv

`lane,coordinate,name,version,wheel,platform_tag,digest,size_bytes`

After repair, digests must match `/app/nuget-cache/index.csv` placeholders (never recomputed
wheel-byte hashes). `size_bytes` MUST match the table in `/app/docs/nuget-contract.md`
(edge `pkg:ledger-metrics` is **3000**, not the starter `8000`). Keep original `version`
strings. Residual rows `pkg:blocked` and `pkg:quarantine` must be present on the edge lane.
Edge residual package row order is normative (byte-stable, not alphabetical):
`pkg:legacy-nuget`, then `pkg:tainted`, then `pkg:blocked`, then `pkg:quarantine`.

## nuget-cache/index.csv

`digest,path,platform_tag` — canonical offline registry placeholders (propagate; do not
recompute from nuget-cache bytes). Must include blocked/quarantine residual nuget-cache artifacts.

## pins.csv

`name,digest,platform_tag` — hashdrift when package digest disagrees.
Must include primaries plus `legacy-nuget`, `tainted`, `blocked`, `quarantine`, `alt-a`, `alt-b`.

## feedtags.csv

`name,expected_tag` — feedtag when package platform_tag disagrees.

After repair MUST include **`blocked`** and **`quarantine`** (`any`). Normative order:
ledger-core/utils/gateway/metrics (`nupkg`), then legacy-nuget/tainted/blocked/quarantine/alt-a/alt-b (`any`).

## peers.csv

`lane,coordinate,peer_name` — packagerefdrift when `peer_name` is absent from package names
present in the lane artifact set. After repair the edge lane MUST include
`edge,pkg:ledger-gateway,ledger-extra`. Do **not** add a `ledger-extra` package.

## advisories.csv / bans.csv / xor.csv

`coordinate,cve` / `coordinate` (triple bans) / `lane,group,package_name`

Keep both gate `mgr-choice` rows and the edge `unused`/`ledger-utils` row.

## TWO DISTINCT residual orderings (read carefully)

- **`edges.csv`** `mid:link → pkg:*` children: `blocked → legacy-nuget → quarantine → tainted`
- **`artifacts.csv`** edge residuals: `legacy-nuget → tainted → blocked → quarantine`

Neither is alphabetical. Bundle share CSVs must match the documented row order exactly.

## graphs/artifacts.csv

`artifacts.csv`: `lane,coordinate`.

### Normative edge hard spine (exact mid names)

`svc:app→mid:bridge→mid:spur→mid:beam→mid:relay→mid:span→mid:stem→mid:ridge→mid:ford→mid:ledge→mid:shelf→mid:crest→mid:cairn→mid:peak→mid:saddle→mid:knoll→mid:col→mid:glen→mid:mesa→mid:keel→mid:tor→mid:crag→mid:rift→mid:dune→mid:heath→mid:scar→mid:mere→mid:holt→mid:vale→mid:apex`

First hard edge row must be `svc:app,mid:bridge,hard`. Then interleaved five-arm fan
(via→fork→wing→yoke→arch) into `mid:link`. Soft decoys after fan and before link
residuals (include `spur→fen`, `holt→vale`, `glen→mesa`, `ford→ledge`). Soft traces last.
Include artifact `mid:fen` after `mid:spur`. Mid-hop artifact rows precede primaries;
traces last. Gate: hop chain first, then `gw:edge→` primaries.

Audit JSON sorts artifacts by coordinate independently of CSV hop order.

## graphs/edges.csv

`edges.csv`: `lane,parent,child,edge_kind` (`hard`|`soft`).

Soft decoys (never cascade), after arm→link and before link residuals:
`mid:apex→mid:via`, `mid:mesa→mid:tor`, `mid:crest→mid:peak`, `mid:ridge→mid:ledge`,
`mid:saddle→mid:knoll`, `mid:col→mid:mesa`, `mid:scar→mid:vale`, `mid:spur→mid:fen`,
`mid:holt→mid:vale`, `mid:glen→mid:mesa`, `mid:ford→mid:ledge`.

Soft paths: `svc:app→trace:soft→pkg:ledger-core`, `svc:app→trace:haze→pkg:ledger-utils`,
`svc:app→trace:mist→pkg:ledger-gateway`, `svc:app→trace:fog→pkg:ledger-metrics`.
