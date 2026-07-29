# Signed envelope contract

Envelopes contain `schema_version`, `payload_type`, base64 `payload`, and non-empty
`signatures` with Ed25519 base64 signatures.

Current signing domain:

```text
"DAC1\0envelope\0" || u32_be(type_len) || type || u64_be(payload_len) || payload_bytes
```

Envelope digest is SHA-256 over canonical envelope bytes without the final newline.
Payload digest is SHA-256 over decoded payload bytes. Subject artifact digests are distinct
and must not be substituted by envelope or payload digests.

An attestation is usable only when its `issued_epoch` is not later than the request
`evaluation_epoch`. Its signing key must be active at both the attestation issue epoch and
the evaluation epoch reconstructed from the request trust state.
