# Row rules

`/app/output/graph_probe.json` is JSON with:

- `edges`: list of edge objects
- `edge_count`: length of `edges`
- `view_digest`: 64-character hex digest of the sorted edges

Each edge object has `module_path`, `version`, `replace_to` (empty string when unused), `cls`, and `sum`.

`view_digest` must match `python3 /app/environment/tools/view_sum.py` on the edges payload.

Workspace `/app/environment/nest/go.sum` must stay aligned with plan edge checksums: each relevant edge contributes a `module_path version sum` line using the edge's original-module checksum.
