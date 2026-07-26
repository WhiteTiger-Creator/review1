FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends r-base-core tmux asciinema && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock && \
    rm /tmp/requirements.lock

COPY docs/ /app/docs/
COPY data/ /app/data/
COPY estimate.R /app/estimate.R
COPY --chmod=0755 run.sh /app/run.sh
RUN mkdir -p /app/outputs
