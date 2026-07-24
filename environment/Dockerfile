FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS gotoolchain

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      patch \
      ca-certificates \
      jq \
      tmux \
      asciinema \
      git \
 && rm -rf /var/lib/apt/lists/*

COPY --from=gotoolchain /usr/local/go /usr/local/go
RUN ln -s /usr/local/go/bin/go /usr/local/bin/go \
 && ln -s /usr/local/go/bin/gofmt /usr/local/bin/gofmt
ENV PATH=/usr/local/go/bin:$PATH \
    GOPATH=/root/go \
    GOCACHE=/root/.cache/go-build \
    GOFLAGS=-mod=mod

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/verifier-venv \
 && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt

WORKDIR /app/environment

COPY go.mod /app/environment/go.mod
COPY requirements.txt /app/environment/requirements.txt
COPY cmd/ /app/environment/cmd/
COPY internal/ /app/environment/internal/
COPY testdata/ /app/environment/testdata/

WORKDIR /app/environment
