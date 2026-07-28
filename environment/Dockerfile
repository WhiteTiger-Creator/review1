FROM golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS build

WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc=4:12.2.0-3 \
    libc6-dev=2.36-9+deb12u13 \
    && rm -rf /var/lib/apt/lists/*

COPY go.mod ./
COPY . .
RUN go mod tidy && CGO_ENABLED=1 go build -o /out/gated ./cmd/gated \
    && CGO_ENABLED=1 go build -o /out/inspect ./cmd/inspect

FROM debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TMUX_TMPDIR=/var/tmp/tmux
ENV PATH=/app/bin:/usr/local/go/bin:${PATH}
ENV GOPATH=/tmp/gopath

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema=2.2.0-1 \
    build-essential=12.9 \
    ca-certificates=20230311+deb12u1 \
    gcc=4:12.2.0-3 \
    ncurses-term=6.4-4 \
    openssl=3.0.20-1~deb12u2 \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    && mkdir -p /var/tmp/tmux /app/bin \
    && chmod 1777 /var/tmp/tmux \
    && printf '%s\n' \
        'export PATH="/app/bin:/usr/local/go/bin:$PATH"' \
        > /etc/profile.d/zz-app-toolchain.sh \
    && printf '%s\n' \
        'export PATH="/app/bin:/usr/local/go/bin:$PATH"' \
        >> /root/.bashrc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/go /usr/local/go

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY runtime/tmux.conf /etc/tmux.conf
COPY --from=build /out/gated /app/bin/gated
COPY --from=build /out/inspect /app/bin/inspect
COPY . /app/environment

RUN chmod +x /app/environment/scripts/*.sh
