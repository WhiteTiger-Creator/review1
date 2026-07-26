# Normalized lineage DOT contract

`lineage.dot` is a Graphviz `digraph` named `Lineage`. It is the canonical,
deterministic serialization of the reconciled lineage. This contract fixes the
**format**; the values themselves follow from the ledger and the dossier.

## Structure

```
digraph Lineage {
  graph [name="reconciled-lineage"];
  "<run_uid>" [id="<run_uid>", label="<run_uid>", feature_path="<path>"];
  ...
  "<parent_uid>" -> "<child_uid>" [annotation="<content>", auc_delta="<decimal>", baseline="<run_uid>"];
  ...
}
```

## Rules

* There is exactly one node per logical run and exactly one edge per logical
  parent→child relationship, regardless of how many source statements described
  it.
* Node identifiers are the ledger's canonical `run_uid`.
* Nodes are emitted sorted by `run_uid`. Edges are emitted sorted by
  `(parent_uid, child_uid)`.
* Node attributes: `id` and `label` equal the `run_uid`; `feature_path` is the
  calibrated feature path, a chain of `run_uid`s. Multi-parent composition is
  bracketed. The construction rule is defined by the dossier.
* Edge attributes: `annotation` is the resolved annotation content;
  `auc_delta` and `baseline` are present only when a qualifying baseline
  exists. `auc_delta` is an exact decimal string with six fractional digits.
* All identifiers and attribute values are double-quoted. Embedded quotes,
  backslashes, and newlines are backslash-escaped so the file parses with the
  installed Graphviz tools (`dot -Tcanon`).
* Output is byte-identical across repeated runs and across swapped worktree
  order. No timestamps, temporary paths, or absolute host/build paths appear.
