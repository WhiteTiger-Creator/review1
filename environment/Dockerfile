FROM golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS builder

WORKDIR /build

COPY go.mod ./
COPY cmd ./cmd
COPY stride ./stride
COPY gate ./gate
COPY phase ./phase
COPY store ./store
COPY engine ./engine

RUN go build -o /build/mirctl ./cmd/mirctl \
    && go build -o /build/viewctl ./cmd/viewctl

FROM debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TMUX_TMPDIR=/var/tmp/tmux
ENV MIRROR_ROOT=/app/environment
ENV PATH=/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends python3=3.11.2-1+b1 \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    curl=7.88.1-10+deb12u15 \
    ncurses-term=6.4-4 \
    openssl=3.0.20-1~deb12u2 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    util-linux=2.38.1-5+deb12u3 \
    && mkdir -p /var/tmp/tmux /app/bin /app/output /logs/verifier /logs/agent \
    && chmod 1777 /var/tmp/tmux \
    && useradd -m -u 1000 -s /bin/bash -U agent \
    && useradd --system --uid 10001 --home-dir /tmp/mirrun-home --create-home \
        --shell /usr/sbin/nologin mirrun \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/go /usr/local/go

RUN printf '%s\n' \
        'export PATH="/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"' \
        > /etc/profile.d/zz-go-toolchain.sh \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY runtime/tmux.conf /etc/tmux.conf
RUN sed -i 's/\r$//' /etc/tmux.conf

COPY go.mod /app/environment/
COPY cmd /app/environment/cmd
COPY stride /app/environment/stride
COPY gate /app/environment/gate
COPY phase /app/environment/phase
COPY store /app/environment/store
COPY engine /app/environment/engine
COPY signal /app/environment/signal
COPY config /app/environment/config
COPY fixtures /app/environment/fixtures
COPY data /app/environment/data
COPY docs /app/environment/docs
COPY scripts /app/environment/scripts

COPY --from=builder /build/mirctl /build/viewctl /app/bin/

RUN find /app/environment -type f \( -name '*.sh' -o -name '*.go' \) -exec sed -i 's/\r$//' {} + \
    && chmod +x /app/environment/scripts/repro_mirror.sh /app/environment/signal/probe.sh \
    && chown -R agent:agent /app/environment /app/bin /app/output /logs/agent \
    && chmod 1777 /app/output \
    && chown -R root:root /opt/verifier-venv /usr/local/go /logs/verifier /logs \
    && chmod -R go-rwx /opt/verifier-venv \
    && chmod 755 /logs \
    && chmod 775 /logs/agent \
    && chmod 700 /logs/verifier \
    && find /usr/local/go -type f -exec chmod a-w {} + \
    && find /usr/local/go -type d -exec chmod 755 {} + \
    && for bin in /usr/bin/python3 /usr/bin/python3.11; do \
         if [ -e "$bin" ]; then chown root:root "$bin"; chmod 555 "$bin"; fi; \
       done \
    && chmod 555 /usr/local/go/bin/go
