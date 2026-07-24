FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

COPY requirements.lock /tmp/requirements.lock
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip tmux asciinema \
    make libssl-dev \
    && pip3 install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Makefile /app/
COPY inc/ /app/inc/
COPY src/ /app/src/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY scripts/ /app/scripts/
COPY benchmarks/ /app/benchmarks/
COPY data/ /app/data/

RUN make clean && make

RUN mkdir -p /app/output

RUN echo 'export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"' >> /root/.bashrc
