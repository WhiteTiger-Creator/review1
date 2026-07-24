# Ranking evaluation protocol

A ranking model assigns a real-valued relevance score to each candidate document of a
query. For scoring, the candidates of a judged query are ordered by descending model
score and compared against the ordering implied by the human relevance grades.

The primary measure is normalized discounted cumulative gain over the top results, with
a gain of `2^grade - 1` for a document at grade `grade` and a logarithmic position
discount. A model that places high-grade documents near the top scores close to one; a
model that orders documents no better than chance scores far lower.

The judged queries used for scoring are held out and are not part of the interaction
logs in `data/`. Their feature vectors are expressed on the canonical basis described in
`data/feature_schema.json`, which is also the basis the production relevance estimator
in `data/logging_ranker.json` is defined on. A model is expected to generalize to those
unseen queries rather than to reproduce the click behaviour on the logged ones.

Alongside ranking quality, the recovered examination propensities are compared against
the examination pattern that actually governed the logged sessions. Examination is a
property of where something sat on the rendered page, so the curve is indexed by page
slot as described in `serp_rendering.md`, and it is compared up to a common scale factor.
