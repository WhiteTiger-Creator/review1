#!/bin/bash
set -euo pipefail
cd /app && ./bin/tuf-rollout-verifier
