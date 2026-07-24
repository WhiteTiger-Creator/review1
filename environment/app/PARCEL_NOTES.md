# Umber Kiln Parcel Engraver — packing notes

These notes are the normative release-kiln packing contract for parcel
inputs under the `PARCELS` directory. The Vala engraver under `/app/engraver`
must satisfy every rule here when deciding whether a kiln run may publish
build products and when rendering those products.

## Make target

```text
make -C /app engrave PARCELS=<parcel-dir> OUT=<out-dir>
```

On a consistent parcel set publish exactly:

- `<out-dir>/crate.index`
- `<out-dir>/seal.manifest`

On any inconsistent condition delete both products (if present), wipe every
non-`.keep` file under `/app/engraving_tmp`, and exit nonzero. Never leave
partial products. Never write anything else into `<out-dir>`.

Scratch files may be created only under `/app/engraving_tmp` and must be
removed before a successful or failed exit so that directory contains only
the `.keep` placeholder.

At the start of every engraving run, clear any prior `crate.index` and
`seal.manifest` under the output directory before validation begins.

## Declared seal tokens

Allowed seal tokens: `KILN_SEAL`, `AMBER_SEAL`, `BRONZE_SEAL`, `UMBER_SEAL`.

A crate seal token outside this set makes the set inconsistent.

### Root seal token on the manifest

The `seal_token` column on `seal.manifest` is the seal token of the root
of the notice-inheritance chain for that crate:

- If the crate does not inherit (`inherited_from` blank), use its own
  `seal_token`.
- If it inherits, walk parents until the root (blank `inherited_from`) and
  use that root crate's `seal_token`.

## Control token

If any `crates.tsv` row has `compression_stamp` equal to `vala_exit`, the
run is a forced Vala failure: clear products, clear engraving chips, and
exit nonzero without publishing. The `vala_exit` token is not required to
appear in `stamps.tsv`.

## Parcel sheets (TSV, TAB separated, header row required)

Ignore blank lines. Trim ASCII whitespace on fields. Parcel inputs are
read-only for the engraver.

### `stamps.tsv`

Columns: `stamp`, `stamp_priority`.

- Every row declares one allowed compression stamp and its positive integer
  priority.
- `stamp` values must be unique.
- A crate `compression_stamp` other than `vala_exit` must appear here.
  Otherwise the set is inconsistent (`unknown_compression_stamp`).

### Family stamp election

Within one `family`, inspect every crate's declared `compression_stamp`
(ignoring `vala_exit`).

Elect the family's stamp as follows:

1. Greatest `stamp_priority` from `stamps.tsv`.
2. On a priority tie, prefer the stamp declared by the crate with the
   lowest `notice_priority` in that family.
3. If still tied, ascending stamp name.

Every crate in that family uses the elected family stamp as its
`index_note`.

### `crates.tsv`

Columns: `crate_id`, `family`, `compression_stamp`, `release_tier`,
`crate_priority`, `seal_token`.

- `crate_id` values must be unique. Repeats make the set inconsistent.
- `crate_priority` is a positive integer.
- `family` is a non-empty token used to join checksum alphabets, notice
  conflict checks, and family stamp election.
- Every `release_tier` must appear in `tiers.tsv`.
- Every `seal_token` must be a declared seal token.

### `shards.tsv`

Columns: `shard_id`, `crate_id`, `shard_order`, `input_name`,
`byte_count`, `shard_digest`.

- `shard_id` values must be unique.
- Every `crate_id` must exist in `crates.tsv`. An orphan shard makes the
  set inconsistent.
- `shard_order` is a positive integer.
- For each `crate_id`, the set of `shard_order` values must be exactly
  `{1, 2, ..., N}` with no gaps and no duplicates.
- `byte_count` is a non-negative integer.
- `shard_digest` is a non-empty token checked against the family alphabet.

### `mirrors.tsv`

Columns: `input_name`, `mirror_id`, `receipt_digest`, `mirror_trust`,
`mirror_priority`.

- `mirror_trust` is `yes` or `no`.
- `mirror_priority` is a positive integer.
- A shard input may be reused only when at least one trusted row matches
  `input_name` and `receipt_digest == shard_digest`.
- If two or more trusted rows for the same `input_name` carry different
  `receipt_digest` values, the set is inconsistent.

### Dominant-shard and mirror selection

1. Dominant shard: greatest `byte_count`; ties break by ascending
   `shard_order`.
2. Among trusted mirrors matching that shard's input and digest, select
   the mirror with the lowest `mirror_priority`.
3. When two or more trusted matches share that lowest `mirror_priority`,
   prefer a `mirror_id` that also appears as a trusted match for every
   other shard of the same crate (same `mirror_id`, matching each shard's
   `input_name` and `shard_digest`). If more than one such affinity
   mirror remains, or none do, break ties by ascending `mirror_id`.

Every non-dominant shard still needs trusted coverage.

### `notices.tsv`

Columns: `crate_id`, `notice_fence`, `inherited_from`, `notice_priority`,
`public_text`.

- Exactly one notice row per `crate_id` in `crates.tsv`.
- `notice_priority` is a positive integer.
- `inherited_from` may be blank.

#### Fence inheritance

- Blank `inherited_from`: effective fence is the crate's own
  `notice_fence`.
- Non-blank: take the ancestor's effective fence after resolving the
  ancestor first. Cycles are inconsistent.

#### Local fence constraint while inheriting

When inheriting, the child's own `notice_fence` must be blank or exactly
equal to the resolved effective fence. Otherwise inconsistent.

#### Chain-folded public seal text

- `local_public` = the crate's own `public_text` (blank →
  `missing_seal_wording`).
- Root: effective public = `local_public`.
- Child of `P`: effective public =
  `P.effective_public + "#" + local_public`
  where `P.effective_public` is the parent's already composed public seal
  text (root-to-leaf order along the inheritance chain).
- The composed string must fit `public_seal_text` width.

#### Family fence harmony

After inheritance, every crate in the same `family` must share one
effective notice fence.

### `lanes.tsv` — candidate bids

Columns: `lane_id`, `crate_id`, `capacity_bytes`, `used_bytes`,
`lane_priority`, `lane_note`.

- A crate may have one or more candidate rows.
- Every crate in `crates.tsv` must have at least one candidate.
- `capacity_bytes` and `used_bytes` are non-negative integers.
- `lane_priority` is a positive integer.
- All rows that share a `lane_id` must agree on `capacity_bytes` and
  `used_bytes`; disagreement is inconsistent.

#### Dependency contribution

For crate `X`, `own(X)` is the sum of its shard `byte_count` values.
`contrib(X) = own(X) + sum(own(A))` over every strict ancestor `A` on the
notice-inheritance chain whose `family` equals `X.family`. Ancestors in a
different family still participate in fence, public-seal, and root-seal
inheritance, but they do not inflate lane load.

Capacity checks and lane bidding use `contrib(X)`. The `byte_total` column
on `crate.index` publishes `own(X)` only.

#### Greedy lane bidding

1. Initialize `fill[lane_id] = used_bytes` for each lane.
2. Visit crates in ascending `notice_priority`, then ascending `crate_id`.
3. For the current crate, consider only its candidate rows where
   `fill[lane_id] + contrib(crate) <= capacity_bytes`.
4. Among feasible candidates, choose the greatest `lane_priority`. On a
   `lane_priority` tie, choose the candidate that minimizes residual
   capacity `capacity_bytes - (fill[lane_id] + contrib(crate))`. If still
   tied, ascending `lane_id`.
5. If no candidate is feasible, the set is inconsistent.
6. Assign that `lane_id` to the crate (this is the `lane_id` published on
   `crate.index`) and add `contrib(crate)` to `fill[lane_id]`.

Exact fill (`fill == capacity` after a placement) is allowed.

### `checksums.tsv`

Columns: `alphabet_id`, `allowed_characters`, `digest_width`,
`checksum_priority`.

- `alphabet_id` matches a crate `family` (exactly one row per family).
- Digests must have length `digest_width` and use only
  `allowed_characters`.

### `tiers.tsv`

Columns: `release_tier`, `predecessor_tier`, `tier_priority`,
`tier_wording`.

- Blank `predecessor_tier` marks a root tier (distance 0).
- Non-inheriting crates must be at a root tier.
- Inheriting crates must satisfy `d_child == d_parent + 1`.

### `widths.tsv`

Columns: `product`, `column`, `width`.

Required `crate.index` columns: `crate_id`, `family`, `shard_count`,
`byte_total`, `lane_id`, `release_tier`, `index_note`.

Required `seal.manifest` columns: `crate_id`, `seal_token`, `mirror_id`,
`notice_fence`, `checksum_alphabet`, `public_seal_text`.

All widths are positive integers.

## Rendering

Both products are UTF-8 text, LF line endings, exactly one trailing
newline at EOF, no CR characters. Data rows are fixed-width fields
concatenated with no separators.

Padding:

- Left-aligned space pad: every field except `crate.index` `shard_count`
  and `byte_total`.
- Right-aligned space pad: `crate.index` `shard_count` and `byte_total`.

Overflow of any field → inconsistent (`index_width_overflow`).

### `crate.index`

Header:

```text
crate_id family shard_count byte_total lane_id release_tier index_note
```

`shard_count` is the number of shards belonging to the crate.
`byte_total` is `own(crate)` as defined under dependency contribution.
`lane_id` is the lane assigned by greedy lane bidding.
`index_note` is the elected family stamp.

Sort: ascending `checksum_priority`, then descending `crate_priority`,
then ascending `crate_id`.

### `seal.manifest`

Header:

```text
crate_id seal_token mirror_id notice_fence checksum_alphabet public_seal_text
```

`seal_token` is the root seal token.
`mirror_id` is the selected dominant-shard mirror.
`notice_fence` is the effective fence after inheritance.
`checksum_alphabet` is the family's `alphabet_id`.
`public_seal_text` is the chain-folded public seal text.

Sort: ascending effective `notice_fence`, then ascending
`notice_priority`, then ascending `crate_id`.

## Determinism

Identical parcel facts must produce byte-identical products even when
sheet rows are reordered.
