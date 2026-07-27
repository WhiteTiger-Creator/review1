# Use the canonical Python base for both stages. The builder adds the pinned
# Debian C toolchain needed to compile the json-c evidence gate.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc=4:12.2.0-3 \
        libc6-dev=2.36-9+deb12u14 \
        libjson-c-dev=0.16-2 \
        make=4.3-4.1 \
        pkg-config=1.8.1-1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Makefile ./
COPY include/ include/
COPY src/ src/
RUN make clean all

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

LABEL org.opencontainers.image.title="RIPEstat FRR failover workbench" \
      org.opencontainers.image.description="FRR operations runtime with RIPEstat evidence and policy tools" \
      org.opencontainers.image.source="local/ris-failover-operations" \
      org.opencontainers.image.version="2.0" \
      org.opencontainers.image.licenses="Proprietary"

COPY requirements.lock /tmp/requirements.lock

# requirements.lock includes the pinned pytest runner and CTRF reporter used
# by the offline verifier.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        ca-certificates=20230311+deb12u1 \
        curl=7.88.1-10+deb12u15 \
        diffutils=1:3.8-4 \
        frr=8.4.4-1.1~deb12u2 \
        jq=1.6-2.1+deb12u2 \
        libjson-c5=0.16-2 \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir \
        --require-hashes -r /tmp/requirements.lock

WORKDIR /app

COPY --from=builder /app/bin/ris-evidence-gate /app/bin/ris-evidence-gate
COPY --chmod=0755 bin/frr-policy-render /app/bin/frr-policy-render
COPY docs/ docs/
COPY etc/ etc/
COPY inventory/ inventory/
COPY policy/ policy/
COPY runbooks/ runbooks/

RUN mkdir -p /app/change/ris
