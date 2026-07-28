# Source: https://doc.rust-lang.org/cargo/commands/cargo-vendor.html
# Retrieved: 2026-07-21
# Title: cargo-vendor(1)
# Bounded task rule: Directory sources produced for vendoring are read-only replacements; use with [source] replace-with for offline locked builds.

cargo vendor vendors crates.io and git dependencies into a local directory.
The configuration necessary to use the vendored sources is emitted for .cargo/config.toml.
Cargo treats vendored sources as read-only.
--locked asserts lockfile agreement; --offline prevents network access.
