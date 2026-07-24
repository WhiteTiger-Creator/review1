#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export GOTOOLCHAIN=local
mkdir -p "${ROOT}/lib"
go build -C "${ROOT}" -trimpath -buildvcs=false -o "${ROOT}/lib/fold-map" ./cmd/fold-map
cat > "${ROOT}/bin/fold-map" <<EOF
#!/bin/bash
exec "${ROOT}/lib/fold-map" "\$@"
EOF
chmod 0755 "${ROOT}/bin/fold-map" "${ROOT}/lib/fold-map"
"${ROOT}/bin/fold-map" --help >/dev/null
TMPNET="$(mktemp /tmp/loadcrest-smoke-XXXXXX.acn)"
cat > "${TMPNET}" <<'NET'
AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1.0 0 0 0 0 0 0 0 0 0
BUS load PQ 1.0 0 0 0 0 0 0.5 0.2 0 0
BRANCH l1 slack load IN 0.01 0.1 0.0 1.0 0
END
NET
"${ROOT}/bin/fold-map" admittance --network "${TMPNET}" >/dev/null
rm -f "${TMPNET}"
