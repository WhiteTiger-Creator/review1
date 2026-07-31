#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:/go/bin:${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
export HOME="${HOME:-/root}"
export GOCACHE="${GOCACHE:-/opt/go-cache}"
export GOPROXY="${GOPROXY:-off}"
export GOSUMDB="${GOSUMDB:-off}"
export GOFLAGS="${GOFLAGS:--mod=mod}"
export GOTOOLCHAIN="${GOTOOLCHAIN:-local}"
export CGO_ENABLED="${CGO_ENABLED:-0}"

GO="${GO_BIN:-/usr/local/go/bin/go}"
DST="/app/opt/hallowspar"
SRC="/solution/reference"

/bin/mkdir -p "$DST"
/bin/rm -f "$DST"/*.go
/bin/cp "$SRC/go.mod" "$DST/go.mod"
/bin/cp "$SRC/tables.go" "$DST/tables.go"
/bin/cp "$SRC/standing.go" "$DST/standing.go"
/bin/cp "$SRC/play.go" "$DST/play.go"
/bin/cp "$SRC/close.go" "$DST/close.go"
/bin/cp "$SRC/sheet.go" "$DST/sheet.go"
/bin/cp "$SRC/main.go" "$DST/main.go"

cd "$DST"
"$GO" build -o /app/bin/hallowspar .
/app/bin/hallowspar
