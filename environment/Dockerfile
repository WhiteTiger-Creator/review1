FROM public.ecr.aws/docker/library/rust:1.85-slim-bookworm@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

ENV PATH="/usr/local/cargo/bin:/usr/local/rustup/bin:${PATH}"
ENV CARGO_HOME=/usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup

# Layer 1: operating packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        patch \
        python3 \
        python3-pip \
        python3-venv \
        tmux \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Layer 2: verifier wheelhouse and lock (installed only by tests/test.sh)
COPY requirements.lock /opt/verifier-requirements.lock
COPY verifier-wheels /verifier-wheels

# Layer 3: Rust manifest, lockfile, Cargo source replacement, and vendored dependencies
COPY spanforge/Cargo.toml spanforge/Cargo.lock /opt/spanforge/
COPY spanforge/.cargo /opt/spanforge/.cargo
COPY spanforge/vendor /opt/spanforge/vendor

# Layer 4: Rust source, modal-code documents, wrapper, build script, and examples
COPY spanforge/src /opt/spanforge/src
COPY spanforge/modal-code /opt/spanforge/modal-code
COPY spanforge/examples /opt/spanforge/examples
COPY spanforge/build-modal-reconciler.sh /opt/spanforge/build-modal-reconciler.sh
COPY spanforge/bin /opt/spanforge/bin
RUN chmod +x /opt/spanforge/build-modal-reconciler.sh /opt/spanforge/bin/modal-reconciler \
    && mkdir -p /opt/spanforge/libexec

# Layer 5: application build
RUN /opt/spanforge/build-modal-reconciler.sh

WORKDIR /workspace
