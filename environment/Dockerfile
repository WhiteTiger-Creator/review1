# Go + Rust digest-pinned toolchains (offline runtime; no network cargo/go fetches).
FROM rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36 AS rust-toolchain

FROM golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TMUX_TMPDIR=/var/tmp/tmux
ENV CARGO_HOME=/usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV PATH=/opt/verifier-venv/bin:/usr/local/cargo/bin:/usr/local/go/bin:$PATH
ENV GOCACHE=/tmp/go-cache
ENV GOPATH=/go

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    make=4.3-4.1 \
    patch=2.7.6-7 \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    && mkdir -p /var/tmp/tmux /app/bin /app/output /app/var /logs/verifier /tmp/go-cache \
    && chmod 1777 /var/tmp/tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
COPY runtime/tmux.conf /etc/tmux.conf
COPY . /app/environment/

RUN cd /app/environment \
    && cargo build --release --manifest-path k7/Cargo.toml \
    && cargo build --release --manifest-path m3/Cargo.toml \
    && install -m 0755 k7/target/release/k7 /app/bin/k7 \
    && install -m 0755 m3/target/release/m3 /app/bin/m3 \
    && go build -o /app/bin/chironymctl ./cmd/chironymctl

WORKDIR /app
