# Agent-built binaries are installed to /app/bin/opsctl and /app/bin/opsd; /app/environment is a symlink to /app.
FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3=3.11.2-1+b1 python-is-python3=3.11.2-1+deb12u1 \
        asciinema=2.2.0-1 \
        bash=5.2.15-2+b13 \
        ca-certificates=20230311+deb12u1 \
        curl=7.88.1-10+deb12u15 \
        jq=1.6-2.1+deb12u2 \
        libsqlite3-dev=3.40.1-2+deb12u2 \
        patch=2.7.6-7 \
        pkg-config=1.8.1-1 \
        procps=2:4.0.2-3 \
        python3-pip=23.0.1+dfsg-1 \
        sqlite3=3.40.1-2+deb12u2 \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir --require-hashes \
        -r /tmp/requirements.txt

RUN mkdir -p /logs/verifier /logs/agent \
    && chmod 777 /logs/verifier /logs/agent

COPY . /app/

RUN cd /app \
    && cargo build --release --locked \
    && mkdir -p /app/bin /app/state \
    && cp /app/target/release/opsctl /app/bin/opsctl \
    && cp /app/target/release/opsd /app/bin/opsd \
    && ln -sfn /app /app/environment \
    && chmod +x /app/scripts/*.sh \
    && /app/scripts/build-fixtures.sh \
    && ln -sfn /usr/local/cargo/bin/cargo /usr/local/bin/cargo \
    && ln -sfn /usr/local/cargo/bin/rustc /usr/local/bin/rustc \
    && ln -sfn /app/bin/opsctl /usr/local/bin/opsctl \
    && ln -sfn /app/bin/opsd /usr/local/bin/opsd \
    && printf '%s\n' \
        'export PATH="/usr/local/bin:/usr/local/cargo/bin:/app/bin:${PATH}"' \
        > /etc/profile.d/kseal-path.sh \
    && chmod 0644 /etc/profile.d/kseal-path.sh \
    && chmod -R a+rwX /app \
    && bash -lc 'command -v cargo && command -v rustc && command -v opsctl && command -v opsd'

ENV RUST_BACKTRACE=1 \
    KSEAL_CONFIG=/app/config/service.toml \
    KSEAL_DB=/app/state/store.db \
    KSEAL_AUDIT=/app/state/store.audit.jsonl \
    CARGO_NET_OFFLINE=true \
    PATH="/app/bin:/usr/local/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

CMD ["sleep", "infinity"]
