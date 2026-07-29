# Source: https://doc.rust-lang.org/cargo/reference/config.html
# Retrieved: 2026-07-21
# Title: Configuration — Config-relative paths
# Bounded task rule: Config-file paths are relative to the parent of the directory containing the config file (for .cargo/config.toml → project root). Env and inline --config paths are relative to the current working directory.

Paths in config files may be absolute, relative, or a bare name without any path separators.
For environment variables, paths are relative to the current working directory.
For config values loaded directly from the --config KEY=VALUE option, paths are relative to the current working directory.
For config files, paths are relative to the parent directory of the directory where the config files were defined.
