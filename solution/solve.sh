#!/bin/bash
mkdir -p /app/src
cp /solution/main.go /app/src/main.go || exit 1
cd /app || exit 1
rm -rf bin
mkdir -p bin
go build -o bin/tan ./src || exit 1
test -x /app/bin/tan || exit 1
echo oracle-build-ok
