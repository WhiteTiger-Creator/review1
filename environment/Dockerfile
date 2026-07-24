FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        patch=2.7.6-7 \
        python3=3.11.2-1+b1 \
        python3-venv=3.11.2-1+b1 \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier
RUN cd /tmp && /opt/verifier/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes --no-deps -r ./requirements.lock
RUN rm -f /tmp/requirements.lock

ENV PATH=/opt/verifier/bin:/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY go.mod /app/environment/go.mod
COPY cmd/ /app/environment/cmd/
COPY internal/ /app/environment/internal/
COPY docs/ /app/docs/
COPY fixtures/ /app/fixtures/

RUN mkdir -p /app/output \
    && go -C /app/environment build -trimpath -o /tmp/nuosc-build-check ./cmd/nuosc \
    && rm -f /tmp/nuosc-build-check

CMD ["bash"]
