#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/tools"

cat > "$ROOT/tools/rivet_gate" <<EOF
#!/bin/bash
set -euo pipefail
ROOT="$ROOT"
export RUBYLIB="\$ROOT/briar/lib:\$ROOT/flume/lib:\$ROOT/kerf/lib\${RUBYLIB:+:\$RUBYLIB}"
exec ruby "\$ROOT/kerf/lib/rivet_main.rb" "\$@"
EOF
chmod +x "$ROOT/tools/rivet_gate"

RUBYLIB="$ROOT/briar/lib:$ROOT/flume/lib:$ROOT/kerf/lib" ruby -e '
  require "briar_rivet"
  require "briar_scan"
  require "flume_kern"
  require "flume_soft"
  require "kerf_pack"
  require "kerf_echo"
'
echo "compile_lane: ready"
