# Canonical Terminal-Bench Go image for Go 1.21-1.26 tasks.
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

LABEL org.opencontainers.image.title="vault-quorum-seal" \
      org.opencontainers.image.description="Offline robust vault quorum recovery" \
      org.opencontainers.image.source="terminal-bench"

ENV DEBIAN_FRONTEND=noninteractive
COPY requirements.lock /tmp/requirements.lock
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        python3 \
        python3-pip \
        tmux \
    && python3 -m pip install --no-cache-dir --break-system-packages --require-hashes --no-deps \
        -r /tmp/requirements.lock \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go \
    && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && rm -rf /var/lib/apt/lists/*

# The verifier intentionally rebuilds the submitted Go source in the runtime image.
WORKDIR /app
COPY app/ /app/
