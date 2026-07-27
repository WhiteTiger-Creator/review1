# Canonical Go runtime base (docs/PLATFORM_AUTO_EVAL.md).
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    GOTOOLCHAIN=local \
    GOPROXY=off \
    CGO_ENABLED=0 \
    HOME=/tmp \
    GOCACHE=/tmp/go-cache

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/deps.in
RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/deps.in

RUN ln -sf /opt/verifier/bin/pytest /usr/local/bin/pytest \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go

ENV PATH=/opt/verifier/bin:/usr/local/go/bin:${PATH}

COPY go.mod /app/environment/go.mod
COPY cmd /app/environment/cmd
COPY docs /app/environment/docs
COPY knot /app/environment/knot
COPY vault /app/environment/vault
COPY sieve /app/environment/sieve
COPY internal /app/environment/internal
COPY packs /app/environment/packs
COPY run /app/environment/run
COPY scripts /app/environment/scripts

RUN mkdir -p /app/bin /app/output /tmp/go-cache \
    && ln -sfn /app/environment/packs /app/packs \
    && ln -sfn /app/environment/docs /app/docs \
    && ln -sfn /app/environment/scripts /app/scripts \
    && chmod +x /app/environment/scripts/build_cqrun.sh \
    && /app/environment/scripts/build_cqrun.sh \
    && chmod a+rwX /app/environment /app/environment/knot /app/environment/vault /app/environment/sieve \
    && chmod a+rwX /app/environment/run /app/environment/cmd /app/environment/internal /app/environment/scripts \
    && chmod a+rwX /app/bin /app/output /tmp /tmp/go-cache \
    && chmod 1777 /app/output /tmp /tmp/go-cache /app/bin

WORKDIR /app
