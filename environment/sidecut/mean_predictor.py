"""Off-path mean label predictor."""
def predict_mean(labels):
    return sum(labels) / len(labels) if labels else 0.0
