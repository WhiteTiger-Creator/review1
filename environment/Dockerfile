FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      tmux \
      asciinema \
      python3 \
      python3-pip \
      python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

ENV PATH="/opt/venv/bin:${PATH}"
ENV GOPROXY=off
ENV GOFLAGS=-mod=mod

WORKDIR /app/environment
COPY go.mod /app/environment/go.mod
COPY main.go /app/environment/main.go
COPY docs /app/environment/docs
COPY schemas /app/environment/schemas
COPY examples /app/environment/examples
