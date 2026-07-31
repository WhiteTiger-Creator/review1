# Canonical Terminal-Bench Rust runtime base (digest-pinned).
# Single-stage is intentional: the verifier rebuilds the candidate crate offline
# after agent edits (`cargo build --release --locked --offline`).
FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        build-essential \
        ca-certificates \
        pkg-config \
        python3 \
        python3-pip \
        python3-venv \
        tmux \
    && rm -rf /var/lib/apt/lists/*

ENV CARGO_HOME="/usr/local/cargo"
ENV RUSTUP_HOME="/usr/local/rustup"
ENV PATH="/usr/local/cargo/bin:/usr/local/rustup/bin:/root/.cargo/bin:/usr/local/bin:/usr/bin:/bin"

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes \
        -r /tmp/requirements.lock

RUN ln -sf /opt/venv/bin/python /usr/local/bin/python \
    && ln -sf /opt/venv/bin/pytest /usr/local/bin/pytest

COPY app/Cargo.toml /app/Cargo.toml
COPY app/Cargo.lock /app/Cargo.lock
RUN mkdir -p /app/src \
    && printf 'fn main() {}\n' > /app/src/main.rs \
    && cargo fetch --locked

COPY app/ /app/
COPY source_snapshots/ /app/source_snapshots/

RUN cargo build --release --locked \
    && rm -f /app/target/release/webauthn-assertion-worker \
              /app/target/release/webauthn-assertion-worker.d \
    && find /app/target/release/.fingerprint /app/target/release/deps -maxdepth 1 \
         \( -name 'webauthn-assertion-worker-*' -o -name 'webauthn_assertion_worker-*' \) \
         -exec rm -rf {} + 2>/dev/null || true

RUN mkdir -p /logs/agent /app/output \
    && command -v cargo \
    && command -v rustc \
    && command -v python3 \
    && cargo --version \
    && rustc --version \
    && /opt/venv/bin/pytest --version

# Daytona/Harbor boot: stay root, no USER agent / ENTRYPOINT.
CMD ["sleep", "infinity"]
