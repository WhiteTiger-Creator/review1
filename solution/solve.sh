#!/usr/bin/env bash
set -e
cp /solution/main.go /app/main.go
cd /app && go build -o /app/wb-tracker .
