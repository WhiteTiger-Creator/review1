# Merge contract

## Value kinds

Supported TOML value kinds in the bounded profile:

- string
- integer
- boolean
- array
- table

## Scalar merge

For strings, integers, and booleans, the later value replaces the earlier value.

Later means:

1. Deeper hierarchical configuration after shallower configuration.
2. Later include after earlier include.
3. Including file after its includes.
4. Environment override after configuration files.
5. Later `--config` override after earlier `--config` override (and after environment).

## Array merge

Arrays are concatenated. Higher-precedence items are placed later in the merged array (Cargo join order).

## Table merge

Tables merge recursively key-by-key using the scalar/array/table rules above.

## Canonical value encoding

When emitting `effective_value_rows.canonical_value`, encode by `value_type`:

| `value_type` | Encoding |
|---|---|
| `string` | Raw string content |
| `integer` | Decimal integer string (example: `"8"`) |
| `boolean` | `"true"` or `"false"` |
| `array` | Compact JSON, no unnecessary whitespace (example: `["-C","opt-level=2"]`) |
| `table` | Compact deterministic JSON object |

Do not emit TOML debug formatting or pretty-printed JSON arrays with spaces
after commas.

## Provenance layers

`merge_layer` is exactly one of: `config_file`, `environment`, `cli`.
Environment overrides use `defining_source = "environment"` with the variable
name only in `environment_override_or_null`.

## Non-semantics

Physical TOML key order is not semantic. Duplicate table headers follow TOML merging as parsed by the `toml` crate used by the auditor.
