# Rollback

The rollback artifact is a byte-for-byte copy of the pre-change integrated FRR configuration. If validation, peer review, or the evidence gate fails, do not partially apply a route-map; restore the entire retained configuration through the normal router change mechanism.
