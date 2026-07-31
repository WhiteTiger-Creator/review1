# Graph and variant schema

A graph pack directory contains graph.json and weights.json.

graph.json fields:

- graph_id: string identifier
- certification_epoch: integer, default 0. When 2, epoch annex rules apply before bound comparison.
- layers: array ordered by id ascending for display only. Execution order is topological by inputs edges.
- Each layer object:
  - id: string unique layer id
  - op: one of input, affine, relu, output
  - inputs: array of layer ids (empty for input)
  - weight_key: string key into weights.json (required for affine)

weights.json maps weight_key to object with w (float reference weight), b (float bias), and optional quant block with dtype int8, scale, zero_point, w_q (int8 storage), b_q (int8 storage).

A variant pack directory contains variant.json referencing graph_id and overriding per-layer quant blocks by weight_key.

Scenario pack scenario.json fields:

- scenario_id: string
- drift_bound: positive float maximum allowed drift at any layer output boundary
- input_interval: object with lo and hi for the input layer id named input in graph.json
