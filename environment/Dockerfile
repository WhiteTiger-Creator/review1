FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TMUX_TMPDIR=/var/tmp/tmux
ENV PYTHONPATH=/app/environment

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        ca-certificates=20230311+deb12u1 \
        tmux=3.3a-3 \
    && mkdir -p /var/tmp/tmux /app/output /app/state /logs/verifier /app/environment \
    && chmod 1777 /var/tmp/tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        numpy==2.3.5 \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5
ENV PATH="/opt/verifier-venv/bin:${PATH}"

COPY docs/ /app/environment/docs/
COPY pmwio/ /app/environment/pmwio/
COPY coalesce/ /app/environment/coalesce/
COPY pretrig/ /app/environment/pretrig/
COPY chargegate/ /app/environment/chargegate/
COPY qualitygate/ /app/environment/qualitygate/
COPY pedtrack/ /app/environment/pedtrack/
COPY fitlab/ /app/environment/fitlab/
COPY artiforge/ /app/environment/artiforge/
COPY reducectl/ /app/environment/reducectl/
COPY runbook/ /app/environment/runbook/
COPY fixturekit/ /app/environment/fixturekit/
COPY fixtures/ /app/environment/fixtures/
COPY hvreduce.py /app/environment/hvreduce.py
COPY OPERATOR.md /app/environment/OPERATOR.md
COPY runtime/tmux.conf /etc/tmux.conf

RUN ln -sf /app/environment /app/environment-link \
    && ln -sfn /app/environment/docs /app/docs \
    && python3 /app/environment/fixturekit/gen_fixtures.py
