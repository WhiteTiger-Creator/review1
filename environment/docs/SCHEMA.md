training_choices.csv has one row per historical choice event. event_id is unique. campaign and logger identify the catalog and collection policy. clicked_item is the observed choice. behavior_propensity is the probability assigned to that product by the event's behavior logger. The four user_feature fields are categorical hashes.

training_candidates.csv has ten rows per training event. item_id is unique within event_id. affinity is a source user-item feature. item_feature_0 is numeric and the remaining item features are categorical hashes.

evaluation_choices.csv and evaluation_candidates.csv follow the same public schema but omit clicked_item and behavior_propensity. Event sets are disjoint from training. Identifiers are opaque and may be replaced consistently during verification. split_manifest.csv records the non-overlapping calendar windows.
