FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

WORKDIR /app

ENV GOFLAGS=-mod=mod \
    GOTOOLCHAIN=local \
    CGO_ENABLED=0 \
    PATH=/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# A login shell sources /etc/profile, which overwrites PATH and drops
# /usr/local/go/bin, so the ENV above is not enough on its own.
RUN printf '%s\n' 'export PATH=/usr/local/go/bin:/go/bin:$PATH' \
        > /etc/profile.d/golang.sh \
    && chmod 0644 /etc/profile.d/golang.sh

RUN apt-get update && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages pytest==8.2.0

COPY go.mod /app/go.mod
COPY src/ /app/src/
COPY docs/ /app/docs/
COPY data/ /app/data/
COPY README.md /app/README.md

RUN go build -o /app/posixmatch ./src
