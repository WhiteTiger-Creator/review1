FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    tmux \
    asciinema \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir \
    pytest==8.3.5 \
    pytest-json-ctrf==0.3.5

COPY app/go.mod /app/go.mod
COPY app/cmd /app/cmd
COPY app/internal /app/internal
COPY app/scenarios /app/scenarios
COPY app/contracts /app/contracts
COPY app/docs /app/docs
COPY app/config /app/config

RUN mkdir -p /app/output /app/bin \
    && go build -o /app/bin/tak-road /app/cmd/tak-road \
    && printf '%s\n' 'export PATH="/usr/local/go/bin:/app/bin:$PATH"' 'export GOROOT=/usr/local/go' >> /root/.bashrc \
    && printf '%s\n' 'export PATH="/usr/local/go/bin:/app/bin:$PATH"' 'export GOROOT=/usr/local/go' >> /etc/profile

ENV PATH="/usr/local/go/bin:/app/bin:${PATH}"
ENV GOROOT=/usr/local/go
