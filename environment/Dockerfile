# Canonical Terminal-Bench Rust runtime base (the rust:1.85-slim family).
# The agent writes Rust in /app and the verifier rebuilds the crate from that source
# before exercising the CLI, so the Rust toolchain deliberately stays in the runtime
# image instead of a builder stage. The crate resolves only the standard library.
FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

ENV CARGO_TERM_COLOR=never \
    CARGO_NET_OFFLINE=true \
    PYTHONDONTWRITEBYTECODE=1 \
    RUST_BACKTRACE=0

# System packages: the agent runtime needs tmux and asciinema, the verifier drives the
# binary from pytest under python3, and the crate is built through make.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        make \
        python3 \
        python3-pip \
        tmux \
    && rm -rf /var/lib/apt/lists/*

# Verifier dependencies, hash-pinned and baked in so nothing is fetched at run time.
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --break-system-packages \
        --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

WORKDIR /app

# Manifests before sources so editing a source file does not disturb earlier layers. The
# crate has no registry dependencies, so the offline build below resolves nothing but std.
COPY app/Cargo.toml app/Cargo.lock app/Makefile /app/
COPY app/docs/ /app/docs/
COPY app/samples/ /app/samples/
COPY app/bin/kxtool /app/bin/kxtool
RUN chmod 0755 /app/bin/kxtool
COPY app/src/ /app/src/

# Warm the build directory and prove the crate compiles as shipped, so the agent starts
# from a project that builds rather than from a broken tree.
RUN make build
