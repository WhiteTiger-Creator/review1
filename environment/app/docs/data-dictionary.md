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

```
name,expected_tag
ledger-core,nupkg
ledger-utils,nupkg
ledger-gateway,nupkg
ledger-metrics,nupkg
legacy-nuget,any
tainted,any
blocked,any
quarantine,any
alt-a,any
alt-b,any
```

## peers.csv

`lane,coordinate,peer_name` — packagerefdrift when `peer_name` is absent from package names
present in the lane artifact set. After repair the edge lane MUST include:

```
lane,coordinate,peer_name
edge,pkg:ledger-gateway,ledger-extra
```

Do **not** add a `ledger-extra` package — the missing peer is intentional residual.

## advisories.csv / bans.csv / xor.csv

`coordinate,cve` / `coordinate` (triple bans) / `lane,group,package_name`

Keep both gate `mgr-choice` rows and the edge `unused`/`ledger-utils` row.

## TWO DISTINCT residual orderings (read carefully)

- **`edges.csv`** `mid:link → pkg:*` children: `blocked → legacy-nuget → quarantine → tainted`
- **`artifacts.csv`** edge residuals: `legacy-nuget → tainted → blocked → quarantine`

Neither is alphabetical. Bundle share CSVs must match the documented row order exactly.

## graphs/artifacts.csv

### Exact edge-lane artifacts.csv row order (byte-stable)

```
lane,coordinate
edge,svc:app
edge,mid:bridge
edge,mid:spur
edge,mid:fen
edge,mid:beam
edge,mid:relay
edge,mid:span
edge,mid:stem
edge,mid:ridge
edge,mid:ford
edge,mid:ledge
edge,mid:shelf
edge,mid:crest
edge,mid:cairn
edge,mid:peak
edge,mid:saddle
edge,mid:knoll
edge,mid:col
edge,mid:glen
edge,mid:mesa
edge,mid:keel
edge,mid:tor
edge,mid:crag
edge,mid:rift
edge,mid:dune
edge,mid:heath
edge,mid:scar
edge,mid:mere
edge,mid:holt
edge,mid:vale
edge,mid:apex
edge,mid:via
edge,mid:fork
edge,mid:wing
edge,mid:yoke
edge,mid:arch
edge,mid:link
edge,pkg:ledger-core
edge,pkg:ledger-utils
edge,pkg:ledger-gateway
edge,pkg:ledger-metrics
edge,pkg:legacy-nuget
edge,pkg:tainted
edge,pkg:blocked
edge,pkg:quarantine
edge,trace:soft
edge,trace:haze
edge,trace:mist
edge,trace:fog
```

## graphs/edges.csv

Edge lane uses a 32-hop hard spine
`svc:app→bridge→spur→beam→relay→span→stem→ridge→ford→ledge→shelf→crest→cairn→peak→saddle→knoll→col→glen→mesa→keel→tor→crag→rift→dune→heath→scar→mere→holt→vale→apex`
The first hard edge row **must** be `svc:app→mid:bridge`. Then interleaved five-arm
fan via/fork/wing/yoke/arch into `mid:link`, plus soft decoys and four soft traces
through `trace:fog`. Soft decoys **after** all arm→link rows and **before**
`mid:link` residual children:
`mid:apex→mid:via`, `mid:mesa→mid:tor`, `mid:crest→mid:peak`, `mid:ridge→mid:ledge`,
`mid:saddle→mid:knoll`, `mid:col→mid:mesa`, `mid:scar→mid:vale`, `mid:spur→mid:fen`,
`mid:holt→mid:vale`.
Soft paths: `svc:app→trace:soft→pkg:ledger-core`, `svc:app→trace:haze→pkg:ledger-utils`,
`svc:app→trace:mist→pkg:ledger-gateway`, `svc:app→trace:fog→pkg:ledger-metrics`.

### Exact edge-lane edges.csv row order (byte-stable)

```
lane,parent,child,edge_kind
edge,svc:app,mid:bridge,hard
edge,mid:bridge,mid:spur,hard
edge,mid:spur,mid:beam,hard
edge,mid:beam,mid:relay,hard
edge,mid:relay,mid:span,hard
edge,mid:span,mid:stem,hard
edge,mid:stem,mid:ridge,hard
edge,mid:ridge,mid:ford,hard
edge,mid:ford,mid:ledge,hard
edge,mid:ledge,mid:shelf,hard
edge,mid:shelf,mid:crest,hard
edge,mid:crest,mid:cairn,hard
edge,mid:cairn,mid:peak,hard
edge,mid:peak,mid:saddle,hard
edge,mid:saddle,mid:knoll,hard
edge,mid:knoll,mid:col,hard
edge,mid:col,mid:glen,hard
edge,mid:glen,mid:mesa,hard
edge,mid:mesa,mid:keel,hard
edge,mid:keel,mid:tor,hard
edge,mid:tor,mid:crag,hard
edge,mid:crag,mid:rift,hard
edge,mid:rift,mid:dune,hard
edge,mid:dune,mid:heath,hard
edge,mid:heath,mid:scar,hard
edge,mid:scar,mid:mere,hard
edge,mid:mere,mid:holt,hard
edge,mid:holt,mid:vale,hard
edge,mid:vale,mid:apex,hard
edge,mid:apex,mid:via,hard
edge,mid:via,mid:link,hard
edge,mid:apex,mid:fork,hard
edge,mid:fork,mid:link,hard
edge,mid:apex,mid:wing,hard
edge,mid:wing,mid:link,hard
edge,mid:apex,mid:yoke,hard
edge,mid:yoke,mid:link,hard
edge,mid:apex,mid:arch,hard
edge,mid:arch,mid:link,hard
edge,mid:apex,mid:via,soft
edge,mid:mesa,mid:tor,soft
edge,mid:crest,mid:peak,soft
edge,mid:ridge,mid:ledge,soft
edge,mid:saddle,mid:knoll,soft
edge,mid:col,mid:mesa,soft
edge,mid:scar,mid:vale,soft
edge,mid:spur,mid:fen,soft
edge,mid:holt,mid:vale,soft
edge,mid:link,pkg:blocked,hard
edge,mid:link,pkg:legacy-nuget,hard
edge,mid:link,pkg:quarantine,hard
edge,mid:link,pkg:tainted,hard
edge,svc:app,pkg:ledger-core,hard
edge,svc:app,pkg:ledger-utils,hard
edge,svc:app,pkg:ledger-gateway,hard
edge,svc:app,pkg:ledger-metrics,hard
edge,svc:app,trace:soft,soft
edge,trace:soft,pkg:ledger-core,soft
edge,svc:app,trace:haze,soft
edge,trace:haze,pkg:ledger-utils,soft
edge,svc:app,trace:mist,soft
edge,trace:mist,pkg:ledger-gateway,soft
edge,svc:app,trace:fog,soft
edge,trace:fog,pkg:ledger-metrics,soft
```
