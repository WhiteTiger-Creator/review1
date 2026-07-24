# Security contract

## Static assets vs runtime state

Immutable / seed assets:

- `/app/etc/privhelper/authority.pub` — Ed25519 public verification key
- `/app/share/privhelper/authority-manifest-v1.json` and `.sig` — generation-1 seed
- `/app/share/privhelper/helpers/*.py` — trusted helper sources
- `/app/share/privhelper/caller-bin/*` — competing caller artifacts restored by `reset`
- `/app/libexec/privhelper/` — live trusted helpers after reset
- `/app/docs/*` — this contract set

Generated runtime state (recreated by `reset`):

- `/app/var/privhelper/authority-manifest.json` + `.sig`
- `/app/var/privhelper/journal.jsonl`, `decisions.jsonl`, `effects.jsonl`, `state.json`
- `/app/reports/*`

Caller artifacts under `/app/var/caller-bin` are part of the incident posture. They must remain present and must not be deleted, chmod-stripped, or overwritten with trusted helpers as a “repair.”

## Requests

Required JSON fields: `request_id`, `principal`, `action`, `unit`. All non-empty, no NUL bytes, unknown fields rejected.

Canonical request digest is SHA-256 over the UTF-8 byte sequence:

```text
"privhelper-request-v1" + NUL +
request_id + NUL +
principal + NUL +
action + NUL +
unit
```

Digest binds all four fields.

Exact retry: same `request_id` with identical canonical body returns the prior committed decision and must not create another effect.

Changed-body conflict: same `request_id` with any changed canonical field returns a conflict denial, does not execute a helper, does not append an effect, and remains visible in the audit trail.

## Signed authority manifest

Current manifest: `/app/var/privhelper/authority-manifest.json`  
Detached signature: `/app/var/privhelper/authority-manifest.sig`  
Public key: `/app/etc/privhelper/authority.pub`

The signature covers the exact manifest file bytes (Ed25519). Signature verification is required every time the current manifest is loaded for a security decision or reconciliation.

`manifest-install` must:

- verify the signature
- require `scenario == "ops-seal"`
- require generation strictly greater than the installed generation
- validate policy and helper schema
- reject absolute helper paths, traversal, empty digests, unsupported interpreters, duplicate semantic entries, and malformed actions
- atomically install manifest and signature together
- leave the previous install untouched on every failure

Equal generation and rollback are rejected. Mutation of the installed manifest after install must be detected on the next load.

Generation-1 policy:

- `ops.owner`: `seal_unit`, `export_bundle`, `rotate_token`
- `ops.operator`: `seal_unit`, `export_bundle`
- `ops.guest`, `ops.auditor`, unknown principals / actions: deny

The dispatcher, not the helper, authorizes. A helper reply never grants authority.

## Helper resolution and execution

Trusted helpers live only under `/app/libexec/privhelper/`.

For each action, use only the manifest helper entry. `relative_path` is a single relative filename (no separators / traversal). Resolve only beneath libexec. Use `Lstat` to reject symlinks. Require a regular file. Reject group-writable or world-writable helpers. Verify the live file digest against the signed manifest entry.

Do not use `PATH`, `HELPER_PATH`, cwd, or caller-provided executable names. Only `/usr/bin/python3` is allowed.

Execute the verified bytes with the absolute interpreter (for example `/usr/bin/python3 -c <verified-bytes>`). Do not reopen an unverified pathname after digest verification.

Use a minimal allowlisted environment. Contaminated caller variables such as `HELPER_PATH`, `PATH`, `PYTHONPATH`, `PYTHONHOME`, `BASH_ENV`, `ENV`, and `LD_PRELOAD` must not be inherited into helper execution and must not alter selected helper identity.

## Helper reply binding

A successful reply is JSON with:

- `status` == `ok`
- `request_digest` equal to the current canonical request digest
- `manifest_generation` equal to the generation used for authorization
- `manifest_digest` equal to the signed manifest digest used for authorization
- `action` and `unit` exactly matching the request
- `effect` exactly matching the manifest helper entry

Malformed or mismatched replies are denials with no privileged effect. The reply must not control the final decision.

## Crash injection

`dispatch --crash-after prepared`: append and sync `prepared`, do not execute the helper, exit non-zero.

`dispatch --crash-after effect`: through append and sync of exactly one effect and `effect_applied`, then exit non-zero without the final decision or `committed`.

## Recovery

`recover` reconstructs from append-only evidence:

- `prepared` with no effect: reauthorize against the currently installed signed manifest. If authority was revoked by a higher generation, record a recovery denial and no effect. If still valid, execute under the current binding exactly once.
- `effect_applied` without commit: verify the existing effect, then finish decision/`committed` exactly once. Never re-execute.
- Exact recovery reruns are idempotent.
- Do not trust stored booleans such as `authorized` or `effect_written` without recomputing evidence.

## Reconciliation

`reconcile` independently re-verifies the installed signature/digest, live helpers, journal-derived request state, decision/effect binding, duplicates, orphans, mismatches, body substitution, unresolved pending work, and journal order contradictions. Counts and digests are derived from live evidence, not stored flags.
