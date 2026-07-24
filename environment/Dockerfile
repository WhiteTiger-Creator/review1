FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       make \
       gcc \
       libc6-dev \
       pkg-config \
       valac \
       libglib2.0-dev \
       python3 \
       python3-pip \
       coreutils \
       findutils \
       gawk \
       tmux \
       asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --no-cache-dir \
    --require-hashes --no-deps -r /tmp/requirements.lock \
    && ln -sf /usr/bin/python3 /usr/bin/python

COPY app/ /app/
WORKDIR /app
RUN make -C /app clean
RUN make -C /app engrave PARCELS=/app/engraver/smoke OUT=/app/out \
    && test -f /app/out/crate.index \
    && test -f /app/out/seal.manifest \
    && make -C /app clean
