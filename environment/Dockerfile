FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS goimg

FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

WORKDIR /app

COPY --from=goimg /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:/usr/local/cargo/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    python3=3.11.2-1+b1 \
    python3-pip=23.0.1+dfsg-1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

COPY . /app/environment

WORKDIR /app/environment
RUN chmod +x /app/environment/exec/*.sh \
    && mkdir -p /app/output /app/bin \
    && cargo build --release -p w2 \
    && (cd /app/environment/q7 && go build -o /app/bin/xq7 ./cmd/xq7)

WORKDIR /app
ENV PATH="/usr/local/go/bin:/usr/local/cargo/bin:/app/bin:/app/environment/exec:${PATH}"
ENV APP_ENV_ROOT=/app/environment
ENV BEAM_OUT=/app/output/span_parity.json
