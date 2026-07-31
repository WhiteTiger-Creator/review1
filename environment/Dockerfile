FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# r-base-core drives the agent-facing analysis; r-cran-jsonlite backs the metrics writer.
# The apt lines carry the accepted non-fatal advisories for this offline task class
# (no version pins, root user, single stage) -- do not "fix" them.
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
      tmux asciinema ca-certificates \
      r-base-core r-cran-jsonlite && \
    rm -rf /var/lib/apt/lists/*

# This venv carries only pytest and the ctrf reporter: every wheel in the lock is
# pure Python, so the hash pins are platform-independent.
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv && \
    /opt/verifier-venv/bin/pip install --no-cache-dir --only-binary=:all: \
      --require-hashes -r /tmp/requirements.lock && \
    rm -f /tmp/requirements.lock

RUN mkdir -p /app/outputs

COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/


