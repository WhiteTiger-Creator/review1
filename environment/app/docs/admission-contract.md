# Admission contract

Evaluation order: parse inputs, verify graph and bytes, verify envelopes, reconstruct trust
state at the evaluation epoch, compute reachable closure, evaluate requirements and thresholds,
reject reachable conflicts, emit canonical decision and evidence, validate, and publish one
generation atomically.
