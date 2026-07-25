FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
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
