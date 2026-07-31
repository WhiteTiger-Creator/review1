FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

LABEL org.opencontainers.image.title="edgekiln-tcpfeat-anvil"
LABEL org.opencontainers.image.description="CDN-edge TCP session quality feature forge (Go)"
LABEL org.opencontainers.image.version="1.0.0"

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV CGO_ENABLED=0
ENV GOTOOLCHAIN=local
ENV PATH="/usr/local/go/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
        tmux \
        asciinema \
        patch \
        jq \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes --no-deps \
        -r /tmp/requirements.lock

COPY go.mod /app/go.mod
COPY cmd /app/cmd
COPY framestream /app/framestream
COPY duplexstitch /app/duplexstitch
COPY tensorloom /app/tensorloom
COPY entropymilli /app/entropymilli
COPY l2anvil /app/l2anvil
COPY kilnemit /app/kilnemit
COPY captureload /app/captureload
COPY qualityemit /app/qualityemit
COPY decoy /app/decoy
COPY docs /app/docs
COPY polbay /app/polbay
COPY netyard /app/netyard
COPY scripts /app/scripts

RUN chmod +x /app/scripts/*.sh \
    && mkdir -p /app/bin /app/qualitycast \
    && ln -sf /app/scripts/rebuild-cdnqual.sh /usr/local/bin/rebuild-cdnqual \
    && /app/scripts/compile-cdnqual.sh

CMD ["sleep", "infinity"]
