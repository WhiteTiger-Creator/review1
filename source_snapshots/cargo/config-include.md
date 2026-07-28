# Source: https://doc.rust-lang.org/cargo/reference/config.html
# Retrieved: 2026-07-21
# Title: Configuration — include
# Bounded task rule: Load include paths left-to-right first (recurse), then merge the including file on top. Paths are relative to the including config file. Optional missing includes are non-fatal.

Configuration can include other configuration files using the top-level include key.
Paths are relative to the configuration file that includes them. Only paths ending with .toml are accepted.
Merge behavior of include:
1. Config values are first loaded from the include paths.
2. Included files are loaded left to right, with values from later files taking precedence over earlier ones. This step recurses if included config files also contain include keys.
3. Then, the config file’s own values are merged on top of the included config, taking highest precedence.
Optional includes use inline table form with optional = true.
