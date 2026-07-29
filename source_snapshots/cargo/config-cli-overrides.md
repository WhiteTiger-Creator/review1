# Source: https://doc.rust-lang.org/cargo/reference/config.html
# Retrieved: 2026-07-21
# Title: Configuration — Command-line overrides
# Bounded task rule: --config KEY=VALUE or path; multiple flags merge left-to-right; CLI takes precedence over environment variables.

Cargo also accepts arbitrary configuration overrides through the --config command-line option.
The argument should be in TOML syntax of KEY=VALUE or provided as a path to an extra configuration file.
The --config option may be specified multiple times, in which case the values are merged in left-to-right order.
Configuration values specified this way take precedence over environment variables, which take precedence over configuration files.
