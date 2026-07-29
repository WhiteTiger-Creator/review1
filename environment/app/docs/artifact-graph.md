# Artifact graph contract

Graph files contain `schema_version`, `artifacts`, and `edges`. Allowed relations:
`contains`, `depends-on`, `built-from`, `packaged-from`, and `derived-from`.

The admission closure is every artifact reachable from the request root, including the root.
Shared dependencies are evaluated once; cycles terminate deterministically; unreachable
artifacts do not affect approval.

The supplied visible release root's reachable closure contains at least `8` artifacts.
Evaluation must cover that entire set; approving a root alone is insufficient.
