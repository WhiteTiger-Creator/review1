FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS lock_build
WORKDIR /src
COPY lock_lane/go.mod lock_lane/main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /lock-release .

FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    TMUX_TMPDIR=/tmp \
    TMPDIR=/tmp \
    GOMAXPROCS=2 \
    LOCK_VAULT_ROOT=/app/lock_vault \
    LOCK_LOG_PATH=/app/output/unwrap_log.jsonl \
    LOCK_STAMP_PATH=/app/output/vault_stamp.txt \
    LOCK_POLICY=/app/lock_vault/custody_policy.yaml

RUN mkdir -p /tmp /var/tmp \
    && chmod 1777 /tmp /var/tmp \
    && apt-get update \
    && apt-get install -y --no-install-recommends asciinema ca-certificates openssl python3 python3-pip tmux unzip \
    && rm -rf /var/lib/apt/lists/* \
    && tmux -V \
    && mkdir -p /tmp/tmux-0 \
    && chmod 700 /tmp/tmux-0

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    cryptography==44.0.0 pytest==8.4.1 pytest-json-ctrf==0.3.5

COPY lock_lane/ /app/lock_lane/
COPY lock_vault/ /app/lock_vault/
COPY --from=lock_build /lock-release /app/bin/lock-release

RUN mkdir -p /app/output /app/bin \
    && chmod 0755 /app/bin/lock-release \
    && test -f /app/lock_lane/main.go \
    && test -f /app/lock_vault/custody_policy.yaml

WORKDIR /app
