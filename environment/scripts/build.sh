#!/usr/bin/env bash
set -euo pipefail

cd /app
mkdir -p /app/bin /app/state /app/output

cat > /app/bin/fyop-atlas << 'EOF'
#!/bin/bash
export PYTHONPATH="/app:${PYTHONPATH:-}"
exec python3 -m fyop "$@"
EOF
chmod +x /app/bin/fyop-atlas

python3 -c "import fyop.cli"
