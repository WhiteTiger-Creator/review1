FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    tmux \
    asciinema \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && pip3 install --break-system-packages --no-cache-dir \
    pytest==8.3.5 \
    pytest-json-ctrf==0.3.5

COPY movement.txt threats.txt signaling.txt power.txt cooperation.txt protocol.txt scoring.txt examples.txt /app/

COPY engine/ /tmp/engine-src/
WORKDIR /tmp/engine-src
RUN CGO_ENABLED=0 go build -o /opt/signal-defense/bin/defensematch ./cmd/defensematch \
    && mkdir -p /opt/signal-defense/contracts \
        /opt/signal-defense/grids \
        /opt/signal-defense/waves \
        /opt/signal-defense/partners \
        /opt/signal-defense/integrity \
        /app/output/generations \
        /logs/verifier \
    && cp -a contracts/. /opt/signal-defense/contracts/ \
    && cp -a grids/. /opt/signal-defense/grids/ \
    && cp -a waves/. /opt/signal-defense/waves/ \
    && cp -a partners/. /opt/signal-defense/partners/ \
    && /opt/signal-defense/bin/defensematch -build-manifest -assets /opt/signal-defense \
    && rm -rf /tmp/engine-src \
    && test -x /opt/signal-defense/bin/defensematch \
    && chmod 755 /opt/signal-defense/bin/defensematch \
    && ln -sf /opt/signal-defense/bin/defensematch /usr/local/bin/defensematch \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go

COPY work/defensebot/ /app/work/defensebot/
WORKDIR /app

ENV PATH="/usr/local/go/bin:/opt/signal-defense/bin:${PATH}"

CMD ["/bin/bash"]
