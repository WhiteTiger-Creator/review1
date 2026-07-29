#!/bin/bash
set -euo pipefail
mkdir -p /app/output /app/output/scratch /app/bin
rm -rf /app/output/scratch/*
rm -f /app/output/peak_report.json
