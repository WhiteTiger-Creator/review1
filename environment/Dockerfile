FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c AS builder
WORKDIR /build
RUN apt-get update \
 && apt-get install -y --no-install-recommends libsqlite3-dev \
 && rm -rf /var/lib/apt/lists/*
COPY app/src/screening_gate.c /build/screening_gate.c
COPY app/include/screening_gate.h /build/screening_gate.h
RUN gcc -std=c17 -O2 -Wall -Wextra -Werror -I/build /build/screening_gate.c -o /build/screening-gate -lsqlite3 -lm

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      asciinema \
      ca-certificates \
      jq \
      openssl \
      sqlite3 \
      tmux \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY app/ /app/
COPY --from=builder /build/screening-gate /app/bin/screening-core
RUN chmod 0755 /app/bin/screening-gate /app/bin/screening-core \
 && chmod 0600 /app/recovery/candidates/*-signing.material \
 && mkdir -p /app/output
