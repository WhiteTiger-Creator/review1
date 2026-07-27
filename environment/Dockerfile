FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

WORKDIR /app/environment

# golang-go remains in the runtime image because the verifier rebuilds
# /app/bin/vcs_sim from /app/environment after agent edits (runtime rebuild carve-out).
RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    golang-go=2:1.19~1 \
    patch=2.7.6-7 \
    tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

COPY config config/
COPY a3 a3/
COPY b7 b7/
COPY c4 c4/
COPY d9 d9/
COPY e5 e5/
COPY j4 j4/
COPY k6 k6/
COPY docs docs/
COPY f6 f6/
COPY g8 g8/
COPY h2 h2/
COPY scenarios scenarios/
COPY go.mod go.mod
COPY README.md README.md

ENV PYTHONPATH="/app/environment" \
    PATH="/app/bin:${PATH}"

RUN mkdir -p /app/bin /app/output state \
    && go test ./... \
    && go build -o /app/bin/vcs_sim ./e5

WORKDIR /app
