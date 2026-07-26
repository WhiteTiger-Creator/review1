# Evidence layout

The change directory contains exactly these regular files:

| Path | Meaning |
| --- | --- |
| `/app/change/ris/01/ipv4.json` through `/app/change/ris/03/ipv4.json` | exact RIPEstat IPv4 response bodies |
| `/app/change/ris/01/ipv4.headers` through `/app/change/ris/03/ipv4.headers` | final IPv4 HTTP response headers |
| `/app/change/ris/01/ipv4.request.json` through `/app/change/ris/03/ipv4.request.json` | chained IPv4 request intent |
| `/app/change/ris/01/ipv4.meta.json` through `/app/change/ris/03/ipv4.meta.json` | ordered IPv4 transfer metadata |
| `/app/change/ris/01/ipv6.json` through `/app/change/ris/03/ipv6.json` | exact RIPEstat IPv6 response bodies |
| `/app/change/ris/01/ipv6.headers` through `/app/change/ris/03/ipv6.headers` | final IPv6 HTTP response headers |
| `/app/change/ris/01/ipv6.request.json` through `/app/change/ris/03/ipv6.request.json` | chained IPv6 request intent |
| `/app/change/ris/01/ipv6.meta.json` through `/app/change/ris/03/ipv6.meta.json` | ordered IPv6 transfer metadata |
| `/app/change/session.json` | pre-acquisition session attestation |
| `/app/change/acquisition.jsonl` | ordered hash-chained ledger of all six captures |
| `/app/change/capture-bindings.jsonl` | length-framed hash chain over exact capture artifacts |
| `/app/change/acquisition-summary.json` | ordered cross-chain acquisition summary |
| `/app/change/acquisition-checkpoints.jsonl` | ordered hash-chained round checkpoints |
| `/app/change/gate-executions.jsonl` | ordered hash-chained ledger of the three gate invocations |
| `/app/change/decisions/01.json` through `/app/change/decisions/03.json` | byte-exact gate outputs for the three rounds |
| `/app/change/decision.json` | derived consensus decision |
| `/app/change/quorum.json` | independently derived authenticated vote tally |
| `/app/change/consensus-certificate.json` | cross-chain consensus certificate |
| `/app/change/rollback.conf` | byte-identical starting FRR configuration |
| `/app/change/frr.conf` | configuration selected by the decision |
| `/app/change/frr-validate-01.log`, `/app/change/frr-validate-02.log` | independent `vtysh` validation outputs |
| `/app/change/render-provenance.json` | ordered renderer and candidate provenance |
| `/app/change/candidate.patch` | byte-exact unified baseline-to-candidate diff |
| `/app/change/candidate-delta.json` | authenticated candidate patch statistics |
| `/app/change/validator-attestation.json` | installed validator identity and version evidence |
| `/app/change/validation.json` | ordered validation attestation |
| `/app/change/source-inputs.sha256` | protected-input provenance manifest |
| `/app/change/bundle-index.json` | ordered payload index |
| `/app/change/bundle-merkle.json` | domain-separated Merkle authentication of the payload index |
| `/app/change/bundle-proofs.json` | critical-payload inclusion proofs |
| `/app/change/signing-public.pem` | fresh Ed25519 public key |
| `/app/change/signing-key.json` | public-key algorithm and fingerprint attestation |
| `/app/change/receipt.sha256` | signed integrity receipt |
| `/app/change/receipt.sig` | raw Ed25519 signature over the exact receipt bytes |
| `/app/change/commit.json` | final ordered bundle commit attestation |

Each round decision retains the gate's documented key order: `change_id`, `decision`, `selected_profile`, `reason`, `query_times`, and `visibility`.

The session object is pretty UTF-8 JSON with a final newline and ordered keys `acquisition_id`, `change_id`, `router`, `endpoint`, `user_agent`, `started_at`, and `policy_sha256`. It is written before any request, and its canonical timestamp is no later than the first transfer start. The endpoint is the RIPEstat endpoint without a query, the User-Agent contains the router and change ID, and the digest authenticates `/app/policy/visibility.conf`.

Each request object is pretty UTF-8 JSON with a final newline and ordered keys `acquisition_id`, `sequence`, `round`, `family`, `resource`, `url`, `user_agent`, `session_sha256`, `previous_request_sha256`, and `request_sha256`. Values agree with the session and acquisition order. `session_sha256` authenticates the exact session bytes. The first predecessor is 64 zeroes and each later predecessor is the prior request hash. The final hash is lowercase SHA-256 of `RIS-REQUEST-V2\0` followed by compact UTF-8 JSON for exactly these nine keys, in this order: `acquisition_id`, `sequence`, `round`, `family`, `resource`, `url`, `user_agent`, `session_sha256`, `previous_request_sha256`. The session and predecessor are therefore part of every request hash canonical.

Each transfer metadata file is pretty UTF-8 JSON with a final newline and ordered keys `acquisition_id`, `sequence`, `round`, `family`, `requested_url`, `effective_url`, `started_at`, `completed_at`, `status_code`, `content_type`, `remote_ip`, `tls_verified`, `http_version`, `redirects`, `bytes_downloaded`, `duration_ms`, `request_sha256`, `headers_sha256`, `body_sha256`, and `semantic_sha256`. The UUID is identical in all six files and is a lowercase RFC 4122 version-4 UUID. Sequence and round/family follow acquisition order. `requested_url` is the endpoint with its single percent-encoded `resource` query; `effective_url` is HTTPS, has host `stat.ripe.net`, path `/data/routing-status/data.json`, and decodes to the same single query. Timestamps follow `change_policy.md`. Status is integer 200 through 299; content type begins with `application/json`; `remote_ip` is a valid plain IPv4 or IPv6 address; `tls_verified` is true; HTTP version is `1.1`, `2`, or `3`; redirects is integer 0 through 3; bytes equals the body length; duration is a nonnegative integer no greater than elapsed client milliseconds plus 1000; and the byte digests authenticate retained artifacts. `request_sha256` binds the request object. `semantic_sha256` is SHA-256 of `RIS-JSON-SEMANTIC-V1\0` followed by the response parsed as JSON and re-encoded as compact UTF-8 with keys recursively sorted, no ASCII substitution, and separators `,` and `:`.

The acquisition ledger is UTF-8 JSON Lines with exactly six newline-terminated compact JSON objects in acquisition order. Ordered keys are `acquisition_id`, `sequence`, `round`, `family`, `resource`, `http_date`, `query_time`, `request_sha256`, `metadata_sha256`, `headers_sha256`, `body_sha256`, `semantic_sha256`, `previous_sha256`, and `entry_sha256`. Values match retained evidence byte-for-byte where they originate as strings: `http_date` is the final response's raw `Date` header value, and `query_time` is the raw JSON `data.query_time` string. Do not convert either value to ISO/RFC 3339, add fractional digits or a timezone suffix, or otherwise normalize it for the ledger. The predecessor chain begins with 64 zeroes. Each entry hash is SHA-256 of `RIS-ACQUISITION-V1\0` followed by compact UTF-8 JSON for the first thirteen ordered keys.

The capture-binding ledger has six compact newline-terminated objects with ordered keys `sequence`, `request_sha256`, `headers_sha256`, `body_sha256`, `metadata_sha256`, `frame_sha256`, `previous_sha256`, and `entry_sha256`. `frame_sha256` hashes `RIS-CAPTURE-FRAME-V1\0` followed, in request/headers/body/metadata order, by each artifact's unsigned 64-bit big-endian byte length and exact bytes. The chain begins with 64 zeroes and each entry hashes `RIS-CAPTURE-CHAIN-V1\0` plus compact JSON of its first seven keys.

The acquisition summary has ordered keys `acquisition_id`, `session_sha256`, `sequences`, `request_tail_sha256`, `acquisition_tail_sha256`, `capture_tail_sha256`, `checkpoint_tail_sha256`, and `summary_sha256`. `sequences` is an ordered six-element array whose objects contain `sequence`, `round`, `family`, `request_sha256`, `acquisition_entry_sha256`, and `capture_entry_sha256`. The tails match their named chains and `summary_sha256` hashes `RIS-ACQUISITION-SUMMARY-V1\0` plus compact JSON of the first seven keys.

The checkpoint ledger has three newline-terminated compact objects, one per completed round, with ordered keys `round`, `last_sequence`, `round_evidence_sha256`, `request_tail_sha256`, `session_sha256`, `acquisition_tail_sha256`, `previous_sha256`, and `entry_sha256`. The round-evidence digest is SHA-256 of `RIS-ROUND-EVIDENCE-V1\0` followed by the raw 32-byte `SHA256(file_bytes)` digest of each request, headers, body, and metadata file in IPv4-then-IPv6 order. This means hashing the exact bytes of all eight named files; an embedded digest field from any of those files is not a file digest and cannot substitute for it. The tails bind the round's IPv6 request and acquisition entry, while the session digest authenticates the exact session bytes. Its predecessor chain begins with 64 zeroes; entries hash `RIS-CHECKPOINT-V2\0` plus compact JSON for their first seven keys.

The gate-execution ledger is UTF-8 JSON Lines with three newline-terminated compact objects in round order. Ordered keys are `sequence`, `round`, `command`, `exit_code`, `stdout_sha256`, `stderr_sha256`, `decision_sha256`, `policy_sha256`, `checkpoint_sha256`, `previous_sha256`, and `entry_sha256`. `command` is the exact five-element absolute-path invocation; exit code is zero; stdout and stderr authenticate empty bytes; the decision digest authenticates retained output; the policy digest authenticates `/app/policy/visibility.conf`; and the checkpoint digest authenticates that round's compact checkpoint line including its newline. The chain begins with 64 zeroes and uses `RIS-GATE-AUDIT-V2\0` plus compact JSON of the first ten keys.

The consensus decision keys are `change_id`, `decision`, `selected_profile`, `reason`, `rounds`, `evidence_chain_sha256`, and `gate_chain_sha256`, in that order. `reason` is `unanimous_apply` when all three rounds apply and `round_hold` otherwise. `rounds` contains `01`, `02`, then `03`; each value contains `decision` then `sha256`. The final two digests authenticate both complete ledgers.

The quorum object keys are `change_id`, `votes`, `apply_count`, `hold_count`, `outcome`, `decision_sha256`, `gate_chain_sha256`, and `quorum_sha256`, in that order. `votes` is an object whose keys are rounds `01` through `03` in that order and whose values are only the plain decision strings from the corresponding retained decision objects (`decision["decision"]`), never the full decision objects; for example, an applying quorum uses `"votes":{"01":"APPLY_STANDBY","02":"APPLY_STANDBY","03":"APPLY_STANDBY"}`. Counts are exact. `outcome` is likewise the plain consensus decision string (`decision.json["decision"]`), for example `"outcome":"APPLY_STANDBY"`, never the consensus object. Both artifact digests authenticate the named files. `quorum_sha256` hashes `RIS-QUORUM-V1\0` plus compact JSON of the first seven ordered keys.

The consensus certificate has ordered keys `change_id`, `outcome`, `decision_sha256`, `quorum_sha256`, `acquisition_summary_sha256`, `checkpoint_chain_sha256`, `gate_chain_sha256`, and `certificate_sha256`. Values authenticate the exact named artifacts, and the final field hashes `RIS-CONSENSUS-CERT-V1\0` plus compact JSON of the first seven keys.

The source-input manifest uses ordinary lowercase `sha256sum` lines, sorted by absolute path, and covers the closed protected-source set exactly once: both regular files in `/app/bin`; all four regular files in `/app/docs`; all three regular files in `/app/etc/frr`; all three regular files in `/app/inventory`; all 15 regular files in `/app/policy`; and all three regular files in `/app/runbooks`. Every source is a non-symlink, single-link regular file, and no other path is present.

The rendering provenance keys are `renderer`, `renderer_sha256`, `source_manifest_sha256`, `baseline_sha256`, `candidate_sha256`, and `reproducible`, in that order. `renderer` is `/app/bin/frr-policy-render`; each digest authenticates the named artifact, and `reproducible` is true. For a hold, reproducible means the selected exact baseline copy was independently compared with the baseline.

`candidate.patch` is the exact output of `diff -u --label /app/etc/frr/running.conf --label /app/change/frr.conf /app/etc/frr/running.conf /app/change/frr.conf`; exit 0 or 1 is accepted. The candidate-delta object has ordered keys `baseline_sha256`, `candidate_sha256`, `patch_sha256`, `added_lines`, `removed_lines`, and `delta_sha256`. Counts include only patch content lines beginning with one `+` or `-`, excluding `+++` and `---` headers. The final field hashes `RIS-CANDIDATE-DELTA-V1\0` plus compact JSON of the first five keys.

The validator attestation has ordered keys `command`, `resolved_path`, `binary_sha256`, `version_command`, `version_output_sha256`, and `attestation_sha256`. The command is `vtysh`, the resolved path is its non-symlink canonical absolute executable, `version_command` is `["dpkg-query","-W","-f=${Version}\\n","frr"]`, and the version digest authenticates that command's exact output. Its final hash uses `RIS-VALIDATOR-V1\0` plus compact JSON of the first five keys.

The validation object keys are `commands`, `exit_codes`, `candidate_sha256`, `logs_sha256`, `logs_match`, `decision_sha256`, `render_provenance_sha256`, `source_manifest_sha256`, `candidate_delta_sha256`, and `validator_attestation_sha256`, in that order. `commands` contains `["vtysh","-C","-f","/app/change/frr.conf"]` twice, both exit codes are zero, `logs_sha256` contains the two named log digests in order, `logs_match` is true, and remaining digests authenticate named artifacts.

The payload set is every retained file except `bundle-index.json`, `bundle-merkle.json`, `bundle-proofs.json`, `signing-public.pem`, `signing-key.json`, `receipt.sha256`, `receipt.sig`, and `commit.json`. The bundle index is a JSON array ordered by absolute path and covers exactly that set. Each object has ordered keys `path`, `sha256`, and `bytes`.

The Merkle object keys are `algorithm`, `leaf_count`, `levels`, and `root_sha256`, in that order. Algorithm is `sha256-domain-separated-v1`. `levels` is the full nested JSON array of lowercase hex digests, not an integer level count: its shape is `[[leaf_0, leaf_1, ...], [parent_0, parent_1, ...], ..., [root]]`. For each index object, the leaf is SHA-256 of `0x00 || UTF8(path) || 0x00 || raw_32_byte_file_digest || uint64_be(bytes)`. Each following array hashes adjacent raw digest pairs as `SHA256(0x01 || left || right)`; duplicate the last digest when odd. The final array contains the single digest also stored as `root_sha256`.

The proof object is pretty JSON whose keys are the absolute paths `/app/change/decision.json`, `/app/change/frr.conf`, `/app/change/source-inputs.sha256`, and `/app/change/validation.json` in that order. Each value has ordered keys `index`, `leaf_sha256`, and `siblings`. Index and leaf match the bundle index and first Merkle level. Siblings are ordered leaf-to-root objects with keys `side` then `sha256`; side is `left` or `right`, and duplicated odd siblings are included. Replaying the node hash reaches the retained root.

Generate a fresh Ed25519 private key only in a temporary file below `/app/change`, export its public key in PEM, and destroy the private key before success. Before the receipt, write `signing-key.json` with ordered keys `algorithm`, `public_key_sha256`, `public_key_der_sha256`, and `signature_target`; values are `Ed25519`, the PEM digest, the SHA-256 of DER SubjectPublicKeyInfo bytes emitted by OpenSSL, and `/app/change/receipt.sha256`. The receipt uses ordinary lowercase `sha256sum` syntax sorted by absolute path and covers every retained file except itself, the signature, and commit. Sign its exact bytes into raw `receipt.sig` and verify with the retained key.

The final commit object has ordered keys `acquisition_id`, `payload_count`, `merkle_root_sha256`, `bundle_index_sha256`, `bundle_proofs_sha256`, `receipt_sha256`, `signature_sha256`, `public_key_sha256`, `signing_key_sha256`, `completed_at`, and `commit_sha256`. It binds the acquisition UUID, index length, Merkle root, and exact named files. `completed_at` is canonical UTC RFC 3339 with six fractional digits and no earlier than every transfer completion. `commit_sha256` is SHA-256 of `RIS-COMMIT-V1\0` plus compact UTF-8 JSON for the first ten ordered keys. Write it only after signature verification.

Every artifact is a non-symlink, single-link regular file. `/app/change`, `/app/change/ris`, all round directories, and `/app/change/decisions` use mode 0750; all retained files use mode 0640. No other entry or temporary acquisition, renderer, validation, or signing artifact remains. `rollback.conf` is byte-identical to `/app/etc/frr/running.conf`. Each `.headers` file contains exactly one final HTTP status block through its terminating blank line.
