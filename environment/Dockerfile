FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS builder

WORKDIR /build

COPY go.mod /build/go.mod
COPY cmd/ /build/cmd/
COPY internal/ /build/internal/

RUN mkdir -p /out \
    && go build -o /out/nfs-acld /build/cmd/nfs-acld

FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV PATH="/usr/local/go/bin:/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tmux \
    asciinema \
    python3 \
    python3-pip \
    python-is-python3 \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --break-system-packages \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

COPY --from=builder /usr/local/go /usr/local/go

RUN ln -sf /usr/local/go/bin/go /usr/local/bin/go \
    && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && printf '%s\n' 'export PATH="/usr/local/go/bin:/usr/local/bin:$PATH"' > /etc/profile.d/go-path.sh \
    && chmod 644 /etc/profile.d/go-path.sh \
    && echo 'export PATH="/usr/local/go/bin:/usr/local/bin:$PATH"' >> /root/.bashrc \
    && echo 'export PATH="/usr/local/go/bin:/usr/local/bin:$PATH"' >> /root/.profile

WORKDIR /app

COPY go.mod /app/go.mod
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY governance/ /app/governance/
COPY systemd/ /app/systemd/
COPY --chmod=0755 scripts/ /app/scripts/
COPY var/ /app/var/
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY --from=builder --chmod=0755 /out/nfs-acld /app/bin/nfs-acld

RUN mkdir -p /app/bin /app/run

CMD ["sleep", "infinity"]
