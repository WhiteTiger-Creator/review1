FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      asciinema \
      ca-certificates \
      python3-venv \
      tmux \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/runtime-venv \
 && /opt/runtime-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

ENV PATH="/opt/runtime-venv/bin:${PATH}"
ENV PYTHONPATH="/app"

COPY fyop/ /app/fyop/
COPY docs/ /app/docs/
COPY yard-alpha/ /app/yard-alpha/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/bin /app/state /app/output \
 && bash /app/scripts/build.sh

WORKDIR /app
