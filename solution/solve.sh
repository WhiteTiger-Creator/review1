#!/usr/bin/env bash
set -euo pipefail

cd /solution
patch -d /app/environment -p1 --batch < oracle.patch
gofmt -w /app/environment/cmd /app/environment/internal
go -C /app/environment test ./...
go -C /app/environment build -trimpath -o /tmp/nuosc ./cmd/nuosc

scratch=$(mktemp -d /tmp/neutrino-resume-smoke.XXXXXX)
trap 'rm -rf "$scratch"' EXIT
/tmp/nuosc \
  --config /app/fixtures/earth_mantle_profile.json \
  --propagation "$scratch/partial-propagation.json" \
  --continuation "$scratch/partial-continuation.json" \
  --reproducibility "$scratch/partial-reproducibility.json" \
  --stop-after-steps 3
/tmp/nuosc \
  --config /app/fixtures/earth_mantle_profile.json \
  --propagation "$scratch/resumed-propagation.json" \
  --continuation "$scratch/resumed-continuation.json" \
  --reproducibility "$scratch/resumed-reproducibility.json" \
  --resume "$scratch/partial-continuation.json"

mkdir -p /app/output
/tmp/nuosc \
  --config /app/fixtures/earth_mantle_profile.json \
  --propagation /app/output/propagation.json \
  --continuation /app/output/continuation.json \
  --reproducibility /app/output/reproducibility.json
