# Evidence and decision format

Evidence is deterministic CBOR with sorted map keys, minimal integer encodings, and no
floating-point values. Nodes are content-identified; edges retain all relevant support paths;
equivalent input orderings must yield byte-identical evidence.

CBOR major-type short form applies for unsigned integers and for text, byte, array, and map
lengths of size `<= 23`. Boolean values use the standard CBOR true/false simple values
(`bool`). Larger lengths use the usual additional-info length prefixes. Four-byte unsigned
integers pack big-endian with bit shifts of `24`, `16`, and `8`.

Published `/output/decision.json` is canonical JSON with `schema_version` 2 and these fields:

- `request_digest` — digest of the evaluated request bytes
- `evaluation_epoch` — logical trust clock from the request
- `root_artifact` — release root digest
- `decision` — `approve` or `reject`
- `reason` — null on approve, diagnostic string on reject when applicable
- `artifact_results` — per-reachable-artifact authorization outcomes (including threshold
  principal sets when thresholds apply)
- `effective_revocations` — revocations active at the evaluation epoch
- `legacy_evidence_used` — legacy receipts actually consumed
- `evidence_digest` — `sha256:` digest of the published `/output/evidence.cbor` bytes

`admission-gateway verify` must reject outputs whose `evidence_digest` does not match the
evidence file, or whose `request_digest` does not match the request.
