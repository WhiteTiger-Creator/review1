# Revocation epochs

Revocations affect evaluation epoch E when `effective_epoch <= E`. Wall-clock time is never
used. Future-effective revocations are recorded but inactive for earlier evaluation epochs.
