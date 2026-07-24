# Terminus requires amd64 for Rust images; skip BuildKit lint that forbids constant --platform.
# check=skip=FromPlatformFlagConstDisallowed

FROM --platform=linux/amd64 public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    asciinema \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    tmux \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier-venv \
 && /opt/verifier-venv/bin/pip install --no-cache-dir \
    pytest==9.0.3 \
    pytest-json-ctrf==0.5.0 \
    PyYAML==6.0.2 \
    ruff==0.12.4

ENV PATH="/opt/verifier-venv/bin:/usr/local/cargo/bin:${PATH}"
ENV CARGO_INCREMENTAL=0

# Stable paths for interactive/login shells (tmux) that may rebuild PATH
# without preserving /usr/local/cargo/bin.
RUN ln -sf /usr/local/cargo/bin/cargo /usr/local/bin/cargo \
 && ln -sf /usr/local/cargo/bin/rustc /usr/local/bin/rustc

COPY app/Cargo.toml app/Cargo.lock /app/
COPY app/.cargo/ /app/.cargo/
COPY app/vendor/ /app/vendor/
COPY app/src/ /app/src/
COPY app/docs/ /app/docs/
COPY app/data/ /app/data/
COPY app/service/ /app/service/

WORKDIR /app

RUN command -v cargo \
 && command -v rustc \
 && command -v python3 \
 && command -v tmux \
 && command -v asciinema \
 && cargo --version \
 && rustc --version \
 && python3 --version \
 && cargo build --release --locked --offline \
 && rm -rf /app/target

RUN mkdir -p /app/output

CMD ["sleep", "infinity"]
