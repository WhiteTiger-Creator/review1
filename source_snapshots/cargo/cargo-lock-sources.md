# Source: https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html
# Retrieved: 2026-07-21
# Title: Cargo.toml vs Cargo.lock (source identity)
# Bounded task rule: Locked registry packages carry source and checksum; reconcile each against the effective terminal replacement source before --locked --offline builds.

Cargo.lock records the exact dependency versions used.
Registry packages include source identifiers and content checksums.
--locked fails if the lockfile would change; --offline restricts resolution to locally available sources.
