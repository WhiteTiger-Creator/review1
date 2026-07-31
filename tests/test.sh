#!/bin/bash
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set."
    exit 1
fi

export PATH="/usr/local/go/bin:/go/bin:${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
export GOCACHE="${GOCACHE:-/opt/go-cache}"
export GOPROXY="${GOPROXY:-off}"
export GOSUMDB="${GOSUMDB:-off}"
export GOFLAGS="${GOFLAGS:--mod=mod}"
export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
export CGO_ENABLED="${CGO_ENABLED:-0}"

mkdir -p /app/bin /app/var/lib/hallowspar
if ! ( cd /app/opt/hallowspar && /usr/local/go/bin/go build -o /app/bin/hallowspar . ); then
    echo "the referee's sources did not build"
    echo 0 > /logs/verifier/reward.txt
    exit 1
fi

export REFEREE_BIN=/app/bin/hallowspar
export REFEREE_SRC=/app/opt/hallowspar
export CROWN_MAIN_ROOT=/app/crown

python3 -m pytest -o cache_dir=/tmp/pytest_cache \
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
