# Source: https://doc.rust-lang.org/cargo/reference/source-replacement.html
# Retrieved: 2026-07-21
# Title: Source Replacement
# Bounded task rule: [source.NAME] with replace-with / directory / local-registry. Follow replacement chains to a terminal source. Replacement sources must contain the same package identities.

A source is a provider that contains crates that may be included as dependencies.
[source.my-vendor-source]
directory = "vendor"
[source.crates-io]
replace-with = "my-vendor-source"
replace-with can chain to another named source.
directory and local-registry are filesystem sources suitable for offline use.
Cargo has a core assumption that the source code is exactly the same from both sources.
