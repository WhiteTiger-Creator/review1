#!/bin/bash
set -euo pipefail
rm -f /app/output/m1_tables.rds /app/output/m2_witness.rds /app/output/residual_scope.json
rm -f /app/output/.chain_cache_*
echo "cache tables cleared"
