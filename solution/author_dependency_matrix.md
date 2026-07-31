# Author-side focused-test dependency matrix (no golden report data)

| test | named behavior | earlier gates made valid by setup | candidate report projection | database projection | starter | Oracle |
|---:|---|---|---|---|---|---|
| 01 | CLI/schema/preflight | n/a | summary.processed count | schema tables present | pass | pass |
| 02 | fatal rollback/cleanup | n/a | no output files | unchanged fingerprint | pass | pass |
| 03 | as_of window + report sort | n/a | assertion_rows order; pending_future | assert-future pending | pass | pass |
| 04 | credential binding | n/a | reason tokens; consume=0 | n/a | pass | pass |
| 05 | strict JSON/duplicates | n/a | client_data_malformed | n/a | pass | pass |
| 06 | ceremony type | valid UTF-8/JSON object | client_data_type_invalid | challenge available | pass | pass |
| 07 | challenge lifetime/replay + inclusive equality | signature/origin/RP/flags for equality case | named challenge reasons; equality accepted | equality challenge consumed | fail* | pass |
| 08 | origin / crossOrigin | valid signature over stable JSON | origin_mismatch / cross_origin_disallowed; consume=0 | challenge available; count unchanged | fail* | pass |
| 09 | authenticator layout/flags | n/a | authenticator_data_malformed | n/a | pass | pass |
| 10 | RP ID hash | valid signature over stable JSON | rp_id_hash_mismatch; consume=0 | challenge available | fail* | pass |
| 11 | original-byte hashing anchor | noncanonical whitespace fixture | assert-whitespace accepted | n/a | fail | pass |
| 12 | ES256 DER | stable JSON accepted path (assert-zero-zero); independent of Test 11 | accepted + invalid_signature cases; consume=0 | count unchanged on reject | fail* | pass |
| 13 | UP policy | resign valid auth path to UP=0 | user_presence_required; consume=1; before/after | challenge consumed; cred unchanged | fail | pass |
| 14 | UV policy | fixture UV-miss/ok | UV reject consume=1; later accept | chal-uv-miss consumed | fail | pass |
| 15 | BS without BE | resign valid path | backup_flags_invalid; consume=1 | cred unchanged | fail | pass |
| 16 | BE immutable | resign BE mismatch | backup_eligibility_changed; consume=1 | cred unchanged | fail | pass |
| 17 | counter advance | fixture chronology | before/after 0→5; mutate=1 | final device count 6 | fail* | pass |
| 18 | zero/zero unsupported | fixture | before/after 0; risk null | n/a | fail* | pass |
| 19 | strict replay quarantine | fixture | replay reason; count unchanged | quarantined; last_used_at preserved | fail | pass |
| 20 | backup_aware risk | fixture + strict variant | risk token / quarantine | backup-b active or quarantined | fail | pass |
| 21 | coupled chronological state | synthetic A/B challenges; defer later secure jobs | step1 accept 20→21; step2 UV consume; step3 already_consumed | cred-backup-b=21; A/B consumption | fail | pass |
| 22 | insertion-order invariance | n/a | candidate-relative report equality | n/a | pass | pass |
| 23 | complete golden comparison | n/a | full report == golden | n/a | fail | pass |
| 24 | idempotence + fatal cleanup | n/a | byte-identical rerun; pretty bytes | fatal fingerprint unchanged | pass | pass |

\*Starter may reach a later named reason after fixture isolation, but still fails the full Oracle contract / NOP gate via hashing, ordering, inclusive expiration, counter policy, and/or authenticated challenge consumption.
