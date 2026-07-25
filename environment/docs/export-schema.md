# Export Schema

/app/output/shunting-sequence.json is the final output.

## Fields

- train_id: from consist
- commands: array of command objects (same structure as validated)
- total_distance_m: sum of edge lengths for all movement commands in this sequence (accounting check only; not a required optimal distance)
- outbound_blocks: object keyed by outbound track id, each value is an array of block objects
- loco_end_track: track where locomotive ends. Closure requires a non-failed path from this track to LEAD. The field need not equal LEAD.

## Outbound Block Object

- destination: destination code
- car_ids: list of car ids in this block

Blocks within each outbound track are ordered according to destination_order from plan.json. Within each block, cars preserve their relative order from the inbound consist (stable sort).

## Source Data

Export must read from /app/state/shunting-validated.json only and must not re-read topology, consist, or plan from the raw yard directory.
