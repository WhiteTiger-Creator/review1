FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages pytest==8.3.4

WORKDIR /app

COPY go.mod /app/go.mod
COPY docs /app/docs
COPY data /app/data
COPY examples /app/examples
COPY src /app/src
