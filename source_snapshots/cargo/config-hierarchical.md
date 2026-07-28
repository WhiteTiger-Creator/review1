# Source: https://doc.rust-lang.org/cargo/reference/config.html
# Retrieved: 2026-07-21
# Title: Configuration — Hierarchical structure
# Bounded task rule: Discover .cargo/config.toml from the invocation directory toward the fixture root; deeper scalars win; arrays join with higher-precedence items later.

Cargo looks for configuration files in the current directory and all parent directories.
If a key is specified in multiple config files, the values will get merged together.
Numbers, strings, and booleans will use the value in the deeper config directory taking precedence over ancestor directories.
Arrays will be joined together with higher precedence items being placed later in the merged array.
