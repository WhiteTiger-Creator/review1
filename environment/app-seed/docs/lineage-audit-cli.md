# lineage-audit command-line contract

`lineage-audit` reconciles two release-candidate worktrees into a single
canonical lineage graph and a discrepancy report. This document is the stable
interface contract for the tool. It defines options, exit codes, diagnostics,
configuration precedence, and stream behavior. It does **not** define the
model-governance policy; that authority is the model-review dossier.

## Synopsis

```
lineage-audit --left DIR --right DIR --ledger CSV --dossier MD --output-dir DIR [--set key=value ...]
lineage-audit --help
lineage-audit --version
```

## Options

| Option | Meaning |
|---|---|
| `--left DIR` | First release-candidate worktree. |
| `--right DIR` | Second release-candidate worktree. |
| `--ledger CSV` | Training-run ledger. |
| `--dossier MD` | Model-review dossier (authoritative governance narrative). |
| `--output-dir DIR` | Directory that receives `lineage.dot` and `discrepancies.json`. |
| `--set key=value` | Override a single configuration key (repeatable). |
| `--help`, `-h` | Print usage to stdout and exit 0. |
| `--version` | Print the version banner to stdout and exit 0. |

Unknown options (for example `--bogus`) are rejected with exit code 1, usage
text on stderr, and no output files. Missing required options behave the same
way.

The left/right argument order must never change the logical result or the
bytes of either output file.

The project builds offline with
`/app/environment/gradlew --offline --no-daemon clean test installDist`.

## Exit codes

| Code | Meaning | Diagnostic tokens (stderr) |
|---|---|---|
| 0 | Success. | — |
| 1 | Usage / I/O error (missing option, unreadable input). | `USAGE` |
| 2 | Input validation failure. | `AMBIGUOUS_ALIAS`, `UNKNOWN_RUN`, `MALFORMED_DOT` |
| 3 | Contradictory evidence across the two worktrees. | `CONFLICTING_PARENTAGE`, `CONFLICTING_METRICS` |

On any non-zero exit, no output file may be created or partially written.

## Streams

* On success, stdout contains exactly one line:
  `lineage-audit: reconciled N nodes, M edges` and stderr is empty.
* On failure, stdout is empty and stderr contains a single line of the form
  `lineage-audit: <TOKEN>: <detail>`.

## Configuration precedence

Effective configuration is resolved per key with the following precedence,
highest first:

1. `--set key=value` overrides on the command line;
2. the branch `.lineage-audit.properties` in each worktree;
3. `config/defaults.properties`.

Recognized keys include `annotation.legacy_attrs` (`accept` or `strict`) and
`alias.namespace`. When both worktrees set the same branch key the shared value
is used; the resolution must not depend on which worktree was passed as
`--left`.

With `annotation.legacy_attrs=accept`, annotations stored in legacy Graphviz
attributes such as `xlabel` / `taillabel` participate in precedence resolution
alongside `label`. With `strict`, only `label` participates. Resolved
annotation content strings are dossier-defined tokens such as
`feature_inheritance` and `warmstart`.

Example branch property files:

```
annotation.legacy_attrs=accept
```

```
annotation.legacy_attrs=strict
```

```
annotation.legacy_attrs=accept
alias.namespace=legacy
```

```
annotation.legacy_attrs=accept
alias.namespace=release
```

A missing ledger path such as `/data/does-not-exist.csv` is an I/O error
(exit code 1) and must leave the output directory empty.

## Atomic output

Both output files are produced together or not at all. A run that fails
validation, parsing, or reconciliation must leave `--output-dir` free of
`lineage.dot`, `discrepancies.json`, and any temporary files.
