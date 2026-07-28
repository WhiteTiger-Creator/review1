CREATE TABLE campaigns (
    campaign_id VARCHAR PRIMARY KEY,
    model_revision INTEGER NOT NULL CHECK (model_revision > 0),
    feature_revision VARCHAR NOT NULL,
    expected_sample_count INTEGER NOT NULL CHECK (expected_sample_count > 0),
    feature_count INTEGER NOT NULL CHECK (feature_count = 9),
    decision_threshold DOUBLE NOT NULL CHECK (decision_threshold > 0 AND decision_threshold < 1),
    abstain_spread DOUBLE NOT NULL CHECK (abstain_spread >= 0 AND abstain_spread < 1),
    bootstrap_replicates INTEGER NOT NULL CHECK (bootstrap_replicates >= 100),
    ece_bins INTEGER NOT NULL CHECK (ece_bins >= 2),
    min_coverage DOUBLE NOT NULL CHECK (min_coverage >= 0 AND min_coverage <= 1),
    min_balanced_accuracy_lower DOUBLE NOT NULL CHECK (min_balanced_accuracy_lower >= 0 AND min_balanced_accuracy_lower <= 1),
    max_brier DOUBLE NOT NULL CHECK (max_brier >= 0),
    max_ece DOUBLE NOT NULL CHECK (max_ece >= 0),
    max_fpr_gap DOUBLE NOT NULL CHECK (max_fpr_gap >= 0),
    max_feature_drift DOUBLE NOT NULL CHECK (max_feature_drift >= 0),
    published BOOLEAN NOT NULL
);

CREATE TABLE samples (
    campaign_id VARCHAR NOT NULL,
    sample_index INTEGER NOT NULL CHECK (sample_index >= 0),
    sample_id VARCHAR NOT NULL,
    site_id VARCHAR NOT NULL,
    device_family VARCHAR NOT NULL,
    label INTEGER NOT NULL CHECK (label IN (0, 1)),
    tile_path VARCHAR NOT NULL,
    roi_x INTEGER NOT NULL CHECK (roi_x >= 0),
    roi_y INTEGER NOT NULL CHECK (roi_y >= 0),
    roi_size INTEGER NOT NULL CHECK (roi_size >= 16),
    intensity_gain DOUBLE NOT NULL CHECK (intensity_gain > 0),
    intensity_offset DOUBLE NOT NULL,
    PRIMARY KEY (campaign_id, sample_index),
    UNIQUE (campaign_id, sample_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

CREATE TABLE model_heads (
    campaign_id VARCHAR NOT NULL,
    head_id VARCHAR NOT NULL,
    head_order INTEGER NOT NULL CHECK (head_order >= 0),
    intercept DOUBLE NOT NULL,
    temperature DOUBLE NOT NULL CHECK (temperature > 0),
    vote_weight DOUBLE NOT NULL CHECK (vote_weight > 0),
    PRIMARY KEY (campaign_id, head_id),
    UNIQUE (campaign_id, head_order),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);

CREATE TABLE model_weights (
    campaign_id VARCHAR NOT NULL,
    head_id VARCHAR NOT NULL,
    feature_index INTEGER NOT NULL CHECK (feature_index >= 0),
    weight DOUBLE NOT NULL,
    PRIMARY KEY (campaign_id, head_id, feature_index),
    FOREIGN KEY (campaign_id, head_id) REFERENCES model_heads(campaign_id, head_id)
);

CREATE TABLE feature_references (
    campaign_id VARCHAR NOT NULL,
    feature_index INTEGER NOT NULL CHECK (feature_index >= 0),
    feature_name VARCHAR NOT NULL,
    reference_mean DOUBLE NOT NULL,
    reference_scale DOUBLE NOT NULL CHECK (reference_scale > 0),
    PRIMARY KEY (campaign_id, feature_index),
    UNIQUE (campaign_id, feature_name),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
);
