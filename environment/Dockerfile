FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TMUX_TMPDIR=/var/tmp/tmux

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends make=4.3-4.1 gcc=4:12.2.0-3 python3=3.11.2-1+b1 \
        libc6-dev=2.36-9+deb12u14 \
        asciinema=2.2.0-1 \
        ca-certificates=20230311+deb12u1 \
        ncurses-term=6.4-4 \
        python3-venv=3.11.2-1+b1 \
        tmux=3.3a-3 \
    && mkdir -p /var/tmp/tmux \
    && chmod 1777 /var/tmp/tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

COPY runtime/tmux.conf /etc/tmux.conf
COPY Makefile /app/environment/Makefile
COPY ci /app/environment/ci
COPY docs /app/environment/docs
COPY fixtures /app/environment/fixtures
COPY include /app/environment/include
COPY util /app/environment/util
COPY v3 /app/environment/v3
COPY w6 /app/environment/w6
COPY x1 /app/environment/x1
COPY y8 /app/environment/y8
COPY z2 /app/environment/z2
COPY drv /app/environment/drv
COPY decoy /app/environment/decoy
COPY runtime /app/environment/runtime

WORKDIR /app/environment
RUN chmod +x ci/build.sh ci/rebuild.sh \
    && ./ci/build.sh \
    && make clean \
    && mkdir -p /app/output /app/var/model /opt/verifier-fixtures \
    && cp -a /app/environment /opt/verifier-fixtures/environment

WORKDIR /app
