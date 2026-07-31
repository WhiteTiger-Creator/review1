# FP32 interval notes

Float intervals treat affine weights and biases as exact values from weights.json without dtype widening.

Negative slopes flip interval endpoint order before adding bias. ReLU layers clamp negative lowers to zero while preserving positive uppers when the input interval crosses zero.

These notes complement /app/docs/interval-walk-rules.md for human reviewers only.
