# Path resolution contract

## Bounded path-bearing keys

- `source.<name>.directory`
- `source.<name>.local-registry`
- `build.target-dir`

## Bases

| Origin | Relative path base |
|---|---|
| Hierarchical or included config file | Parent of the directory containing the defining file. For `X/.cargo/config.toml` the base is `X`. For `X/shared/base.toml` the base is `X`. For `X/project/config/source.toml` the base is `X/project`. When the base is the fixture root itself, `base_path` is the empty string `""`. |
| Environment override | Absolute invocation directory for the request |
| Inline `--config KEY=VALUE` | Absolute invocation directory for the request |
| `--config` file override | Parent of the directory containing that file |

## Normalization

1. Join base + raw path when raw is relative.
2. Lexically normalize `.` and `..`.
3. Reject normalized paths that escape the fixture root (`stage = path`, `reason = path_escape`).
4. Equivalent relative spellings must normalize to one semantic path string (slash-normalized, no trailing slash except root).

Absolute raw paths are normalized and still checked against the fixture root bound.
