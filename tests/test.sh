#!/bin/bash
# Verifier dependencies are baked into environment/Dockerfile; nothing is installed here.
set -uo pipefail

mkdir -p /logs/verifier

# Fail loudly rather than silently scoring zero if the image has no WORKDIR set.
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Set a WORKDIR in the Dockerfile."
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

# Rebuild the workbench from the agent's own source so a dropped-in binary cannot pass.
cd /app && make clean >/dev/null 2>&1 || true
make build >/tmp/kxtool-build.log 2>&1 || cat /tmp/kxtool-build.log
chmod -R a+rX /app/bin 2>/dev/null || true

# Run from /tests (a read-only mount the agent cannot write) with PYTHONSAFEPATH so the
# working directory is never placed on sys.path.
cd /tests
PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -c /dev/null --confcutdir=/tests -p no:cacheprovider --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?
if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
