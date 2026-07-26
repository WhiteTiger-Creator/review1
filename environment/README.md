# Search interaction dataset

This directory holds a slice of interaction logs from a document search service and a
small Go project that turns those logs into a relevance ranking model.

## Layout

- `data/impressions/` — one file per collection day. Each row is a single organic result
  the retrieval stack returned for a query: the query it belonged to, the one-based
  `serp_rank` the stack returned it at, the document that filled it, and whether it was
  clicked. Rank is an ordinal produced upstream of the page renderer, so it records the
  ordering the retrieval stack emitted rather than a coordinate on the rendered page.
- `data/features/` — feature vectors for every query and document pair that appears in
  the logs, sharded by query range. Columns `f0` through `f11` are ranking features. The
  pairing key is `(query_id, doc_id)`.
- `data/queries.csv` — per-query metadata: the collection day, the page template the
  result page was rendered with, and how many organic results that page carried.
- `data/documents.csv` — per-document metadata: an approximate length in tokens and a
  coarse source bucket.
- `data/serp_templates.json` — the slot map the renderer applies for each page template,
  described in `serp_rendering.md`.
- `data/extractor_releases.csv` — which build of the feature extractor served each
  collection day.
- `data/logging_ranker.json` — the feature weights of the production relevance estimator
  that ordered the retrieval stack output.
- `data/feature_schema.json` — the feature column names, the canonical basis the features
  are defined on, and the click and rank field names.

## The ranking project

`rank/` is a Go module. When built and run it reads the logs, features and page metadata
and writes a ranking model to `/app/output/ranker.json`. The model file carries a
relevance weight per feature and an examination propensity per page slot. `rank/model.go`
holds the estimator that currently returns a placeholder model; `rank/main.go` handles
reading the data and writing the output and does not need to change.

Relevance grading conventions are described in `relevance_scale.md`; how result pages are
assembled is described in `serp_rendering.md`; how ranking models are scored is described
in `evaluation_protocol.md`.
