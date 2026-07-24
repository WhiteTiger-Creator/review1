FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

# AC continuation / voltage-collapse operator notes (also in /loadcrest/bluebook/):
# fold-map admittance --network <abs.acn>
# fold-map trace --network <abs.acn> --ramp <abs.rmp> --map <abs.vcm>
# POWER-12 failure codes: E_PATH E_NETWORK_DECK E_ISLAND E_BASEPOINT
#   E_BASE_REACTIVE_LIMIT E_CONTINUATION E_REACTIVE_EVENT E_FOLD E_MAP
# POWER-11 admittance JSON: format admittance-companion-v1 plus network_sha256,
#   base_mva, bus/branch counts, slack_bus, nonzero_ybus_entries, ybus, branch_primitives
# TRACE-12 .vcm Store ZIP order: manifest.json, curve.csv, events.csv,
#   critical_bus.csv, critical_branch.csv

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GOTOOLCHAIN=local \
    PATH="/loadcrest/bin:/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# 1) operating packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        patch \
        python3 \
        python3-pip \
        python3-venv \
        tmux \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go \
    && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && printf '%s\n' 'export PATH="/loadcrest/bin:/usr/local/go/bin:/go/bin:$PATH"' > /etc/profile.d/loadcrest-path.sh

# 2) Go module metadata
WORKDIR /loadcrest
COPY loadcrest/go.mod loadcrest/go.sum ./

# 3) task source, bluebooks, wrapper, build script, and examples
COPY loadcrest/ /loadcrest/

# 4) application build
RUN chmod 0755 /loadcrest/build-fold-map.sh \
    && mkdir -p /loadcrest/bin /loadcrest/lib \
    && /loadcrest/build-fold-map.sh \
    && test -x /loadcrest/lib/fold-map \
    && test -x /loadcrest/bin/fold-map \
    && test -f /loadcrest/bluebook/grid-physics.md \
    && test -f /loadcrest/bluebook/continuation-map.md
