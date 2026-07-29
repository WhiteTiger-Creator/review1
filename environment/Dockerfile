# Canonical Terminal-Bench Rust base (digest-pinned).
# Single-stage is intentional: the agent and verifier must compile Rust offline
# at runtime (cargo build --release --locked --offline).
# Run as root — no USER agent / ENTRYPOINT (Daytona Harbor boot).
FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_TERM_COLOR=never \
    CARGO_NET_OFFLINE=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        python3 \
        python3-pip \
        ca-certificates \
        tar \
        gzip \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/output /logs/verifier /logs/agent

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --break-system-packages --no-cache-dir \
        --require-hashes \
        -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

WORKDIR /app
COPY app/ /app/
RUN chmod a+rwx /app/output

# Sanity: starter builds locked offline; fixture packages present.
# Runtime toolchain stays in-image because agents rebuild the auditor.
RUN set -eu \
    && cd /app/auditor \
    && cargo build --release --locked --offline \
    && test -x /app/auditor/target/release/cargo-config-source-replacement-precedence-auditor \
    && test -f /app/fixture-tree/config-root/project/workspace/Cargo.lock \
    && test -d /app/fixture-tree/config-root/project/workspace/vendor-primary \
    && test -d /app/fixture-tree/config-root/project/workspace/local-registry \
    && rm -rf /app/auditor/target \
    && mkdir -p /app/output \
    && chmod a+rwx /app/output

CMD ["sleep", "infinity"]
