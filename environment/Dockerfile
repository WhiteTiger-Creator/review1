FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS builder

WORKDIR /build
COPY bandit/ ./
RUN mkdir -p /out && go build -o /out/ips-eval ./cmd/ipseva

FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV PATH="/usr/local/go/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux asciinema python3 python3-pip ca-certificates \
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out/ips-eval /app/bin/ips-eval
COPY bandit/ /app/bandit/
COPY data/ /app/data/
COPY features/ /app/features/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY models/ /app/models/

RUN mkdir -p /app/output /logs/verifier
