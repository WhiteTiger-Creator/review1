FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY src /build/src
RUN gcc -O2 -s -o /build/stewd /build/src/stewd.c \
    && gcc -O2 -s -o /build/steward /build/src/steward.c

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux asciinema procps \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock
COPY --from=builder /build/stewd /build/steward /usr/local/bin/
COPY fixtures/srv /srv
COPY fixtures/opt /opt
RUN chmod 755 /usr/local/bin/stewd /usr/local/bin/steward \
    && find /srv /opt -exec touch -d '2026-07-26 08:00:00' {} + \
    && mkdir -p /app
WORKDIR /app
