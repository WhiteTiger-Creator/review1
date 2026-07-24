FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        python3 \
        python3-pip \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --break-system-packages \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

ENV GOTOOLCHAIN=local
ENV GOFLAGS=-mod=mod

RUN printf '%s\n' 'export GOPATH=/go' 'export PATH=/go/bin:/usr/local/go/bin:$PATH' \
        > /etc/profile.d/10-golang.sh \
    && chmod 0644 /etc/profile.d/10-golang.sh \
    && ln -sf /usr/local/go/bin/go /usr/local/bin/go \
    && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && bash -lc 'command -v go && command -v gofmt' \
    && sh -lc 'command -v go'

WORKDIR /app

COPY data /app/data
COPY rank /app/rank

RUN cd /app/rank && go build -o /tmp/prewarm . && rm -f /tmp/prewarm
