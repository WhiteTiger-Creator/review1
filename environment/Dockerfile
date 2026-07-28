# Exact canonical Terminal-Bench Go entry from Dockerfile & Image Best Practices §2.
# This task intentionally keeps the Go toolchain in the final stage because agents rebuild Go/C sources.
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV DEBIAN_FRONTEND=noninteractive \
    CGO_ENABLED=1 \
    GOTOOLCHAIN=local \
    GOPROXY=off \
    GOSUMDB=off

# One bounded package transaction supplies the harness and verifier runtime.
# SQLite is provided by Python's standard library, so no pip download is needed.
RUN apt-get -o Acquire::Retries=2 \
        -o Acquire::http::Timeout=60 \
        -o Acquire::https::Timeout=60 update \
    && apt-get -o Acquire::Retries=2 \
        -o Acquire::http::Timeout=60 \
        -o Acquire::https::Timeout=60 install -y --no-install-recommends \
        asciinema \
        file \
        libfftw3-dev=3.3.10-1 \
        patch \
        python3 \
        python3-numpy=1:1.24.2-1+deb12u1 \
        python3-pytest=7.2.1-2 \
        tmux \
    && test -x /usr/local/go/bin/go \
    && ln -sf /usr/local/go/bin/go /usr/bin/go \
    && /usr/local/go/bin/go version \
    && python3 -c "import numpy, pytest; assert numpy.__version__ == '1.24.2'; assert pytest.__version__ == '7.2.1'" \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/go.mod app/go.sum /app/
RUN go mod verify

COPY app/ /app/
RUN install -m 0755 /app/tools/sqlite_bridge.py /usr/local/bin/orbit-registry \
    && ln -sf /usr/local/bin/orbit-registry /usr/local/bin/orbit-seed \
    && mkdir -p /app/data /app/out /app/bin /app/build \
    && /usr/local/bin/orbit-seed --schema /app/db/schema.sql --manifest /app/fixtures/seed.json --db /app/data/orbit.sqlite3 \
    && /usr/local/bin/orbit-registry export --db /app/data/orbit.sqlite3 >/tmp/catalog.json \
    && python3 -m json.tool /tmp/catalog.json >/dev/null \
    && rm -f /tmp/catalog.json

# Harbor creates /tests, /oracle, and /logs mount targets after startup.
# Keep the default runtime user so that bootstrap can create those reserved paths.
# The container remains sandboxed and receives no privileged capabilities.
WORKDIR /app
