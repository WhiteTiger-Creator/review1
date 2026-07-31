FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

RUN ln -sf /usr/local/go/bin/go /usr/local/bin/go && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt

RUN apt-get update -o Acquire::Retries=8 && apt-get install -y --no-install-recommends \
        tmux \
        asciinema \
        ca-certificates \
        make \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir --retries 5 --timeout 60 \
        pytest==8.4.1 pytest-json-ctrf==0.3.5

ENV GOTOOLCHAIN=local

WORKDIR /app

COPY docs/ /app/docs/
COPY Makefile /app/Makefile
COPY src/ /app/src/
