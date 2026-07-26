A search service logged which documents users clicked on its result pages, with feature vectors per query and document pair. Complete the Go program in /app/rank to train a relevance ranking model and write it to /app/output/ranker.json. It gets rebuilt from source and rerun before the model file is read, so a file written any other way is discarded.

The file needs relevance_weights, one per feature column on the canonical basis the judged queries use, not the units the logged values carry. It needs slot_propensities, one per slot of the rendered page, each the chance a reader examines that slot, indexed by where a result was displayed rather than the rank the logs record.

Weights are judged on held out judged queries the logs do not contain rather than on the logged clicks, propensities against the examination pattern behind the logged sessions.

A click happens only when a reader examines the slot a result sat in and also finds that document relevant.
