FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
        binutils \
        strace \
        tmux \
        asciinema \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/verifier-venv

COPY requirements.lock /tmp/requirements.lock
RUN /opt/verifier-venv/bin/python -m pip install --no-cache-dir --require-hashes \
    -r /tmp/requirements.lock

COPY --chown=65534:65534 task_file/ /app/task_file/
RUN mkdir -p /app/task_file/calibration
RUN chown 65534:65534 /app/task_file/calibration
RUN chown 65534:65534 /app
