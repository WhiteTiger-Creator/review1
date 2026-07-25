# Emit contract

Graded artifact: `/app/output/evidence_bundle.tar`

## Desk command

```bash
/app/environment/scripts/compile_lane.sh
/app/environment/tools/rivet_gate \
  --pack /app/environment/fixtures/ax025_pack \
  --db /app/output/shift_ledger.db \
  --bundle-out /app/output/evidence_bundle.tar
```

Members:
- `certificate.json`
- `manifest.json`

## certificate.json fields

- `selection_trace`: JSON array of objects `{ "epoch": int, "probe_id": string }` in MI-greedy pick order.
- `inclusion_digest`: lowercase hex sha256 over UTF-8 lines joined by `\n` (no trailing newline). Each line is `probe_id|lo0,lo1,lo2|hi0,hi1,hi2` for overapprox enclosure corners, sorted by `probe_id` ascending. Floats use exactly 6 decimal places.
- `algebra_digest`: lowercase hex sha256 over UTF-8 lines `arm|KEEP` or `arm|REJECT` for every distinct arm in the pack, sorted by arm ascending.
- `replay_journal`: JSON array of objects `{ "epoch": int, "fingerprint": string, "marker": string }` for the current pack fingerprint only.
- `coverage_band`: (number of arms with KEEP) / (number of distinct arms), 6 decimal places.

## manifest.json

- `certificate.json`: lowercase hex sha256 of raw `certificate.json` bytes
- `manifest.json`: lowercase hex sha256 of the compact JSON object containing only the `certificate.json` entry (no self key), same serializer as `kerf_json.rb`

## Pack probe rows

Each `*.jsonl` line is one PMI probe object with keys `id`, `arm`, `epoch`, `unsafe`, `feats` (three floats in `[0,1]`).

Pack fingerprint: sorted `relative_path|byte_length` lines hashed with sha256.

## shift_ledger.db

- `fixture_catalog` lists each pack `*.jsonl` assembly file and its `source_id`. The gate must keep catalog rows aligned with files present under the pack directory.
- `replay_journal` holds differential replay markers for the active pack fingerprint only. Preloaded foreign fingerprint rows (for example `FOREIGN_PACK_ZZ`) must be removed before emit completes.

During emit the gate may write `/app/output/scratch/soft.txt` as a non-graded soft metric side record.

Enclosure (obligation #14, annex slice 25):
1. Selected unsafe probes define an axis-aligned box.
2. Expand each side by margin `0.050000`.
3. Clamp into `[0.000000, 1.000000]`.
4. Arm KEEP iff every unsafe probe in that arm lies inside the enclosure.
5. Obligation holds when every arm is KEEP.

MI-greedy budget: pick exactly `8` probes (or all if fewer). Bin edges for feature[0]: `0.00, 0.25, 0.50, 0.75, 1.00` (rightmost bin closed). Mutual information uses the natural logarithm (base `e`, i.e. `Math.log` / `math.log`). Tie-break probe_id ascending.
