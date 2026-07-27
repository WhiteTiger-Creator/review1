#!/bin/bash
set -uo pipefail

# Check if we're in a valid working directory
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /logs/verifier

cd /tests && env -i HOME=/tmp LANG=C.UTF-8 LC_ALL=C.UTF-8 PATH=/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA -c /dev/null --rootdir=/tests --confcutdir=/tests --import-mode=importlib -p no:cacheprovider
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
