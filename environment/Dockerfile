FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS builder

ENV GOTOOLCHAIN=local
ENV GOPROXY=off
ENV CGO_ENABLED=0
ENV GOFLAGS=-buildvcs=false

WORKDIR /src
COPY protected/go.mod protected/go.sum ./
RUN go mod download
COPY protected/cmd/ ./cmd/
COPY protected/internal/ ./internal/
RUN go build -trimpath -ldflags="-s -w -buildid=" -o /out/raidscrubctl ./cmd/raidscrubctl

FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

WORKDIR /app

COPY requirements.lock /tmp/requirements.lock
RUN apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
        asciinema=2.2.0-1 \
        ca-certificates=20230311+deb12u1 \
        mdadm=4.2-5 \
        python3=3.11.2-1+b1 \
        python3-pip=23.0.1+dfsg-1 \
        smartmontools=7.3-1+b1 \
        tmux=3.3a-3 \
    && python3 -m pip install --break-system-packages --no-cache-dir \
        --require-hashes --no-deps -r /tmp/requirements.lock \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python3 -c "import pytest, ctrf" \
    && python -c "import pytest, ctrf" \
    && tmux -V \
    && asciinema --version \
    && mdadm --version \
    && smartctl --version \
    && rm -rf /var/lib/apt/lists/* /tmp/requirements.lock

RUN mkdir -p /opt/raid-scrub/bin /app/output /logs/verifier
COPY --from=builder /out/raidscrubctl /opt/raid-scrub/bin/raidscrubctl
COPY docs/raid-contract.txt /app/raid-contract.txt
COPY docs/array-inventory.txt /app/array-inventory.txt
COPY docs/acceptance.txt /app/acceptance.txt
COPY docs/scenarios.txt /app/scenarios.txt
COPY docs/examples.txt /app/examples.txt
COPY work/raid-root/ /app/work/raid-root/

RUN chmod 0755 /opt/raid-scrub/bin/raidscrubctl \
    && chmod a-w /opt/raid-scrub/bin/raidscrubctl \
    && chmod a-w /app/raid-contract.txt /app/array-inventory.txt /app/acceptance.txt /app/scenarios.txt /app/examples.txt \
    && /opt/raid-scrub/bin/raidscrubctl self-test \
    && /opt/raid-scrub/bin/raidscrubctl model-digest \
    && test ! -e /usr/local/go/bin/go \
    && test ! -d /src

ENV PATH="/opt/raid-scrub/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV RAID_ROOT=/app/work/raid-root
ENV RAID_OUTPUT=/app/output

WORKDIR /app
CMD ["/bin/bash"]
