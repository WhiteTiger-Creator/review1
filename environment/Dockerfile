FROM public.ecr.aws/docker/library/ubuntu:24.04@sha256:0d39fcc8335d6d74d5502f6df2d30119ff4790ebbb60b364818d5112d9e3e932

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        lsof \
        perl \
        python3 \
        python3-flask \
        python3-jsonschema \
        python3-pytest \
        strace \
        tmux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/ /app/api/
COPY docs/ /app/docs/
COPY keyring/ /app/keyring/
COPY requests/ /app/requests/
COPY runtime/ /app/runtime/
COPY bin/ /app/bin/
