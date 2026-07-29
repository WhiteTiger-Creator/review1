# Release request contract

Current requests are canonical JSON with fields: `schema_version`, `evaluation_epoch`,
`root_artifact`, `artifact_graph`, `envelopes`, `trust_roots`, `principals`, `policy`,
`event_history`, `legacy_receipts`, and `output_profile`.

Rules: schema version 2; evaluation epoch is the sole trust clock; paths resolve relative
to the request directory; envelope and graph order are semantically irrelevant; existing
`/output` is never an input; conflicting duplicate semantic objects reject.
