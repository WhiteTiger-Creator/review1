# Wasm host architecture

The host separates compiled artifact caching from linked import-plan caching.
Compiled entries are keyed by module identity and the pinned runtime fingerprint wasmtime-29.0.1-cranelift-portable.
Linked plans are keyed by the full security context including tenant, manifest, policy, and grant digests.
Each invocation receives fresh Store state and metering counters.
