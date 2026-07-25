#!/usr/bin/env bash
set -euo pipefail

/opt/julia/bin/julia --startup-file=no -e '
    include("/app/src/policy_load.jl")
    include("/app/src/csv_load.jl")
    include("/app/src/compensate.jl")
    include("/app/src/weights.jl")
    include("/app/src/report_emit.jl")
'

mkdir -p /app/bin
cat > /app/bin/pabcal <<'EOF'
#!/usr/bin/env bash
exec /opt/julia/bin/julia --startup-file=no /app/pabcal.jl "$@"
EOF
chmod +x /app/bin/pabcal

cat > /app/pabcal <<'EOF'
#!/usr/bin/env bash
exec /app/bin/pabcal "$@"
EOF
chmod +x /app/pabcal
