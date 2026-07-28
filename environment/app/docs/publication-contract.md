# Release publication contract

`orbit-certify` accepts only `--db`, `--api`, `--publish-dir`, and optional positive `--timeout-ms` (default 5000). The database and publication directory are absolute paths. The API is a plain HTTP origin with no credentials, path, query, or fragment. Argument failures exit 2. Catalogue, model, HTTP, numerical, timeout, or publication failures exit 3.

The UTF-8 report schema is `orbital-ensemble-release/v1`. It uses two-space indentation, no HTML escaping, nine-decimal rounding with negative zero normalized to zero, fixed field order, and one trailing newline. Fields are, in order: `schema_version`, `campaign_id`, `model_revision`, `feature_revision`, `release_status`, `content_sha256`, `fftw_version`, `sample_count`, `coverage`, `balanced_accuracy`, `balanced_accuracy_ci95`, `brier_score`, `ece`, `fpr_gap`, `max_feature_drift`, `gates`, `heads`, `cohorts`, `feature_drift`, and `samples`. Nested report field names and order are defined by `/app/docs/release-schema.json`. Arrays preserve registry/evaluation order: model-head order, site order, feature index, and sample index.

Each `heads[].sha256` is the lowercase SHA-256 of one compact UTF-8 JSON object with no whitespace and no trailing newline. Its fields occur exactly in this order: `head_id`, `head_order`, `intercept`, `temperature`, `vote_weight`, `weights`. `weights` contains the nine binary64 values in feature-index order. String escaping and floating-point number text follow Go `encoding/json.Marshal`: finite binary64 values use the shortest decimal representation that round-trips to the same value, with lowercase `e` exponent notation when needed. The digest covers only those compact object bytes, not the surrounding release object.

`content_sha256` is the lowercase SHA-256 of the same canonical indented report encoded with `content_sha256` set to the empty string. `fftw_version` is the base dotted numeric release taken from the linked FFTW runtime string: remove text through the `fftw-` marker and remove the first following hyphen and everything after it. For example `fftw-3.3.10-sse2-avx` is published as `3.3.10`.

A generation lives at `/app/out/releases/{content_sha256}/release.json`. `/app/out/current.json` is the same two-space-indented canonical JSON form used for the release, with no HTML escaping and one trailing newline. Its keys occur exactly in this order and use these exact names and values:

```json
{
  "schema_version": "orbital-publication/v1",
  "campaign_id": "<campaign_id>",
  "model_revision": <model_revision_integer>,
  "generation": "<content_sha256>",
  "release": "releases/<content_sha256>/release.json",
  "provenance": "releases/<content_sha256>/provenance.dot"
}
```

The generation's `provenance.dot` is UTF-8 and has exactly the following line order, two leading spaces on every statement, no blank lines, and one newline after the final brace. Placeholder label values are quoted with Go `strconv.Quote`/JSON string escaping. Head lines are appended in model-head order with zero-based indices.

```text
digraph orbital_release {
  graph [rankdir=LR];
  node [shape=box];
  campaign [label="campaign <campaign_id>"];
  model [label="model revision <model_revision>"];
  features [label="features <feature_revision>"];
  metrics [label="status <release_status>"];
  release [label="sha256 <content_sha256>"];
  campaign -> features;
  campaign -> model;
  features -> metrics;
  model -> metrics;
  metrics -> release;
  head_0 [label="<head_0_id> <head_0_sha256>"];
  head_0 -> model;
  ... one node and edge pair for each remaining head ...
}
```

Publication is serialized by `/app/out/.publish.lock`. A new generation is fully written and flushed in a temporary directory, renamed into place, and followed by an atomic current-manifest replacement and directory flush. An existing generation must be byte-identical. Failures preserve the previous current manifest and remove temporary files. Concurrent and repeated unchanged runs create one generation and byte-identical current state.
