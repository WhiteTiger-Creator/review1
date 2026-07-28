# Source: https://doc.rust-lang.org/cargo/reference/source-replacement.html
# Retrieved: 2026-07-21
# Title: Local Registry Sources
# Bounded task rule: local-registry root contains index/ (crates.io-index format) and *.crate archives; verify index record, archive SHA-256, manifest identity, and safe archive paths.

A local registry source is a subset of another registry source available on the local filesystem.
Local registries contain a number of *.crate files as well as an index directory with the same format as the crates.io-index.
