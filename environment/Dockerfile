FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        ca-certificates=20230311+deb12u1 \
        file=1:5.44-3 \
        jq=1.6-2.1+deb12u2 \
        patch=2.7.6-7 \
        python3=3.11.2-1+b1 \
        python3-pip=23.0.1+dfsg-1 \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages \
    --require-hashes --no-deps -r /tmp/requirements.lock

# Dependency manifests + crate sources, then contiguous fetch/vendor/build.
COPY app/Cargo.toml app/Cargo.lock app/rust-toolchain.toml /app/
COPY app/crates/ /app/crates/

# Agent/verifier rebuild at runtime; keep toolchain in-image (known carve-out).
RUN cargo fetch --locked \
    && cargo vendor vendor >/dev/null \
    && mkdir -p .cargo \
    && printf '%s\n' \
       '[source.crates-io]' \
       'replace-with = "vendored-sources"' \
       '' \
       '[source.vendored-sources]' \
       'directory = "vendor"' \
       '' \
       '[profile.release]' \
       'opt-level = 1' \
       'lto = false' \
       'codegen-units = 256' \
       '' \
       '[build]' \
       'jobs = 2' \
       > .cargo/config.toml \
    && cargo build --workspace --release --locked --offline -p admission-gateway \
    && mkdir -p /app/bin \
    && printf '%s\n' '#!/bin/bash' 'exec /app/target/release/admission-gateway "$@"' > /app/bin/admission-gateway \
    && chmod 755 /app/bin/admission-gateway

COPY app/config/ /app/config/
COPY app/docs/ /app/docs/
COPY app/fixtures/ /app/fixtures/
COPY app/requests/ /app/requests/
COPY app/scripts/ /app/scripts/

RUN chmod 755 /app/scripts/build-gateway.sh /app/scripts/run-admission.sh /app/scripts/check-admission.sh

ENV CARGO_NET_OFFLINE=true
ENV PATH="/app/bin:${PATH}"

RUN mkdir -p /output
