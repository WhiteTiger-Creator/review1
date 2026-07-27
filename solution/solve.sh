#!/bin/sh
set -eu
install -m 0644 /solution/main.cpp /app/src/main.cpp
make -C /app clean all
