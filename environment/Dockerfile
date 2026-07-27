FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive

COPY requirements.lock /tmp/requirements.lock
RUN apt-get update && \
    apt-get install -y --no-install-recommends r-base-core tmux asciinema util-linux && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock

WORKDIR /app
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY analysis.R /app/analysis.R
COPY --chmod=0755 run.sh /app/run.sh
