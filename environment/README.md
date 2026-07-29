# FPS lane match replay engine

The `qd` binary replays level manifests under `w8/d7/` for terminal FPS practice scoring. Match lineage, HUD rules, and playthrough tick order are in `p9/q1.contract`.

The container uses the canonical digest-pinned Go 1.24 bookworm image listed in the platform auto-eval base image table (`golang:1.24-bookworm@sha256:1a6d4452…ea77ac` via `public.ecr.aws/docker/library/`).
