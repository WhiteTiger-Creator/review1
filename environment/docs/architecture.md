# Architecture

## Components

| Module | Responsibility |
|--------|----------------|
| `config` | Load trust policy JSON |
| `json_util` | Parse metadata JSON and emit canonical form |
| `crypto` | SHA-256 digests and Ed25519 signature verification |
| `verifier` | Multi-stage TUF pipeline |
| `report` | Serialize rollout report |

## Pipeline stages

1. Load trust policy, rollout lanes, and parse reference time.
2. Load and verify root metadata; extract keys and role delegations.
3. Verify timestamp, snapshot, and targets signatures with deduplicated keyid counting.
4. Validate timestamp→snapshot→targets hash chain using canonical re-serialization of parsed metadata documents (closed freeze intervals use an inclusive end bound).
5. Verify target payload hashes and compute lane, freeze, and rollout eligibility. Allowed-lane lists are inventory metadata and do not gate rollout.
6. Emit structured JSON report with summary rollups; persistence may reseal report_digest from the emitted target array.

## Data flow

```
trust_policy.json ──► config echo + expiry/freeze clock
rollout_lanes.json ──► per-target lane assignment
root.json ──► keys/roles ──► signature verification for all roles
snapshot.json ──► active snapshot version + targets.json hash link
targets.json ──► target entries + rollout custom metadata
target files ──► payload hash verification
```
