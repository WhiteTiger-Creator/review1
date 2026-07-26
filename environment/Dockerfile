FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    jq=1.6-2.1+deb12u2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY kernel-fortify /app/kernel-fortify
COPY lib /app/lib
COPY config /app/config
COPY control /app/control
COPY traces /app/traces
COPY ground-canon /app/ground-canon
COPY docs /app/docs
COPY README.md /app/README.md
COPY CHANGELOG.md /app/CHANGELOG.md

RUN sed -i 's/\r$//' /app/kernel-fortify /app/lib/*.sh \
    && chmod +x /app/kernel-fortify /app/lib/*.sh \
    && mkdir -p /app/output

LABEL org.opencontainers.image.source="https://github.com/snorkel-ai/harbor"
LABEL org.opencontainers.image.description="Kernel lockdown fortify gate for satellite ground-station sysctl hardening"
LABEL org.opencontainers.image.created="2026-07-24T00:00:00Z"
LABEL org.opencontainers.image.revision="1"
LABEL org.opencontainers.image.version="1.0"
LABEL org.opencontainers.image.licenses="MIT"

CMD ["sleep", "infinity"]
