#!/usr/bin/env bash
set -euo pipefail

install -m 0644 /solution/fixed/schedule/enumerate.go /app/internal/schedule/enumerate.go
install -m 0644 /solution/fixed/schedule/coalesce.go /app/internal/schedule/coalesce.go
install -m 0644 /solution/fixed/dispatch/dependency.go /app/internal/dispatch/dependency.go
install -m 0644 /solution/fixed/recovery/recover.go /app/internal/recovery/recover.go

gofmt -w \
  /app/internal/schedule/enumerate.go \
  /app/internal/schedule/coalesce.go \
  /app/internal/dispatch/dependency.go \
  /app/internal/recovery/recover.go
