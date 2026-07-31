# Journal schema

The file at /app/output/skew_journal.json is a JSON object. Top-level key rev_traces holds one object per executed schema_revs entry from the catalog. Top-level key edge_traces holds one object per boundary fixture under fixtures/edges/. Top-level key replay_rows holds prediction rows from a second identical full run on the first successful non-reject revision.

Each revision or edge object reports several properties.

Field rev_id is the catalog or edge fixture id string.

Field gen is the revision integer used for that entry.

Field offline_geom is the sixteen hex lowercase FNV-1a digest of the offline resolved bytes and must match online_geom on accepted revisions.

Field online_geom is the sixteen hex lowercase FNV-1a digest of the online resolved bytes and must match offline_geom on accepted revisions.

Field chan_digest is the sixteen hex lowercase FNV-1a of resolved bytes after bind and fill on the offline path.

Field gate_code uses zero for accept and two for hard-fail forbidden removal.

Field pred_rows is an array of objects with integer t and number v. Accepted runs use length three. Rejected runs use an empty array.

Geometry digests must match exactly. Prediction values must stay within absolute tolerance 1e-9.

Replay_rows must match pred_rows from that second identical run.

Forbidden removal revisions set gate_code to two, leave pred_rows empty, and leave geometry fields as empty strings when the gate rejects before scoring.

Accepted revisions set gate_code to zero and populate digests plus pred_rows.

Id rev_base means the baseline revision whose case path is fixtures/revs/base.json.

Id rev_rename means the rename revision whose case path is fixtures/revs/rename.json.

Id rev_add means the additive nullable revision whose case path is fixtures/revs/add.json.

Id rev_drop means the forbidden-removal revision whose case path is fixtures/revs/drop.json.

Id rev_twice means the alternate baseline payload revision whose case path is fixtures/revs/twice.json.

Id edge_empty means the empty boundary fixture at fixtures/edges/empty.json and must yield gate_code two.

Id edge_reorder means the shuffled-order baseline fixture at fixtures/edges/reorder.json and must match baseline digests for the same values.

Id edge_mixed means the partially remapped revision-one fixture at fixtures/edges/mixed.json and must follow revision-one name maps.
