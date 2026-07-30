FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        coreutils \
        python-is-python3 \
        python3 \
        python3-pip \
        strace \
        tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock

RUN python3 -m pip install --no-cache-dir --break-system-packages --require-hashes \
    -r /tmp/requirements.lock

WORKDIR /app

COPY Cargo.toml Cargo.lock /app/
COPY src/ /app/src/
COPY state/ /app/state/
COPY README.md /app/README.md

RUN cargo build --release
