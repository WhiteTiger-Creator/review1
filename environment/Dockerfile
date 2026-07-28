# Canonical Snorkel ECR Python 3.13 runtime.
FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        pytest==9.0.3 \
        pytest-json-ctrf==0.5.0

WORKDIR /app

COPY docs /app/docs
COPY fixtures /app/fixtures
COPY latchml /app/latchml
COPY featbank /app/featbank
COPY metriclab /app/metriclab
COPY sidecut /app/sidecut
COPY decoy /app/decoy
COPY schemas /app/schemas
COPY binx /app/binx
COPY scripts /app/scripts
COPY verifier-fixtures /opt/verifier-fixtures

RUN chmod +x /app/binx/hwml /app/scripts/run-eval.sh \
    && mkdir -p /app/state /app/plaque

ENV PATH="/opt/verifier-venv/bin:/app/binx:${PATH}"
ENV PYTHONPATH="/app"
