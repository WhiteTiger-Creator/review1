FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages pytest==8.2.0 pytest-json-ctrf==0.5.2 kuzu==0.6.1

WORKDIR /app

COPY graph/ /app/graph/
COPY docs/ /app/docs/
COPY bin/ /app/bin/
