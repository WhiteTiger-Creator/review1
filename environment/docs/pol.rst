# Floating-point numeric policy for case 0708

## Annex byte window
- Magic prefix: ASCII `HZ8` then a zero byte (4 bytes total).
- Next byte: chunk count N.
- Each chunk: endian tag (1 = little-endian samples, 2 = big-endian samples), then u16 little-endian payload length, then payload bytes.
- Payload is a sequence of (x, y) sample pairs. Each sample is u16; byte order follows the chunk tag.
- If the buffer ends before the declared payload length is fully present, the case status must be `reject` and the pack must not claim green for that case.

## Widening thresholds
- Read weights from `/app/data/wts.tsv` columns `a`, `b`, `c` keyed by case id.
- For each decoded sample (x, y), form the box `[x-a, x+a] x [y-b, y+b]`, then clamp each edge into `[0, c]`.
- Held-out rotations from the `rot` table shift (x, y) by (ax, ay) before the same box rule; apply that box rule to every rotation-shifted point as well as to each base sample. Every rotation-shifted point must stay inside `[0, c]` (no obligation holes). If any rotated point falls outside `[0, c]`, the pack `verdict` must be `fail` (not `green`).
- Let `lo_x` and `hi_x` be the minimum and maximum x edges, and `lo_y` and `hi_y` the minimum and maximum y edges, taken over all clamped boxes from base samples and from rotation-shifted points. These four values are the widen envelope for the case.
- Cap rule: widen-radii half-diagonal `sqrt(a*a + b*b)` must be `<= W_CAP * max(a, b)` with W_CAP = 1.5. Field `cap_bound` stores `W_CAP * max(a, b)` written with six decimal places. Digest input is the tuple `(cid, lo_x, hi_x, lo_y, hi_y)` formatted with six decimal places, joined with commas, then SHA-256 hex.

## Lyapunov decrease margin
- Margin M = 0.05.
- For each ledger row `(rid, v_pre, v_post, delta, col_tag)`, posterior contraction requires `v_post <= v_pre - M`.
- Row-ledger invariant: `| (v_pre - v_post) - delta | <= 1e-9` for every row. Matching column sums alone is not enough.
- `violations` counts rows that miss contraction or the row-ledger invariant. Obligation 7 requires zero violations on non-reject cases.

## Pack fields
- Top-level: `schema` (`hz-pack-1`), `cases` (array), `pack_digest` (SHA-256 hex over the canonical case lines), `verdict` (`green` only when every trunc case is `reject`, every other case is `ok` with zero violations and `ledger_mode=row`, radii stay within the cap rule, and every held-out rotation stays inside `[0, c]`; otherwise `fail`).
- Each case: `cid`, `status` (`ok` or `reject`), `hex_pair` (means concatenated decoded x/y as 4-digit hex pairs), `widen_digest` (means sha256 of the six-decimal box tuple), `row_digest` (SHA-256 of row ledger lines), `clf_blob_hex` (means hex of a UTF-8 blob starting with `v=0;mode=row`), `violations` (integer), `cap_bound` (float equals W_CAP*max(a,b)), `ledger_mode` (`row` when row invariants bind; `sum` is insufficient).
- Fixture id `hz_tr` means the truncated WARC case in `/app/docs/cid.txt`.
