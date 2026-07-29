# Canonical Python base (the verifier lane is always pytest regardless of
# task language). rustc/cargo, the task's own subject language, come from
# Debian bookworm's apt repo on top of it — rotctl has zero external crate
# dependencies, so no cargo registry access is ever needed, offline or not.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        cargo \
        rustc \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

WORKDIR /app

COPY app/ /app/
