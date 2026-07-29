# Source: https://doc.rust-lang.org/cargo/reference/config.html
# Retrieved: 2026-07-21
# Title: Configuration — Environment variables
# Bounded task rule: For foo.bar use CARGO_FOO_BAR. Environment variables take precedence over TOML configuration files.

Cargo can also be configured through environment variables in addition to the TOML configuration files.
For each configuration key of the form foo.bar the environment variable CARGO_FOO_BAR can also be used.
Keys are converted to uppercase, dots and dashes are converted to underscores.
Environment variables will take precedence over TOML configuration files.
