# Design vault

Path: /app/state/design_vault.json

Scheme hwml.vault/v1. The vault is the durable snapshot written immediately after
design expansion. Later stages must reload this file from disk rather than trusting
an in-memory design object.

Required fields:

- scheme, identity, column_names, rows, source_trace_count, policy_epoch

rows must match /app/state/design_matrix.json rows (same id order, columns, targets).
source_trace_count equals the number of specimen lines loaded for the vault pass.
policy_epoch echoes the workbook integer and must match during forecast.

Row order is ascending by specimen id string.
---

Scheme id: hwml.vault/v1

Row sequence is ascending by specimen id. Digests use on-disk SHA-256 hex.
