FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3=3.11.2-1+b1 python3-venv=3.11.2-1+b1 python-is-python3=3.11.2-1+deb12u1 \
        asciinema=2.2.0-1 \
        ca-certificates=20230311+deb12u1 \
        git=1:2.39.5-0+deb12u3 \
        jq=1.6-2.1+deb12u2 \
        patch=2.7.6-7 \
        pkg-config=1.8.1-1 \
        sqlite3=3.40.1-2+deb12u2 \
        tmux=3.3a-3 \
        util-linux=2.38.1-5+deb12u3 \
        build-essential=12.9 \
        libsqlite3-dev=3.40.1-2+deb12u2 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash agent

RUN printf '%s\n' \
        'export PATH="/usr/local/cargo/bin:${PATH}"' \
        > /etc/profile.d/rust-toolchain-path.sh \
    && chmod 0644 /etc/profile.d/rust-toolchain-path.sh

COPY . /app/

RUN chmod 0755 /app/tools/rootfs-probe /app/scripts/*.sh \
    && rm -f /app/rust-toolchain.toml /app/.cargo/config.toml \
    && mkdir -p /opt/cargo /home/agent/.cargo \
    && cargo vendor --locked /opt/cargo/vendor \
    && printf '[net]\noffline = true\n\n[source.crates-io]\nreplace-with = "vendored-sources"\n\n[source.vendored-sources]\ndirectory = "/opt/cargo/vendor"\n' > /opt/cargo/config.toml \
    && cp /opt/cargo/config.toml /home/agent/.cargo/config.toml \
    && chown -R agent:agent /home/agent/.cargo \
    && chmod -R a-w /opt/cargo/vendor \
    && CARGO_HOME=/opt/cargo CARGO_NET_OFFLINE=true cargo build --release --locked --offline --workspace \
    && mkdir -p /output /opt/task-fixtures/pristine /var/lib/mint \
    && cp -a /app/fixtures /app/cases /opt/task-fixtures/pristine/ \
    && chown root:root /opt/task-fixtures \
    && chmod 0711 /opt/task-fixtures \
    && chmod -R a+rX /opt/task-fixtures/pristine \
    && find /opt/task-fixtures/pristine -type f -exec chmod a+r {} \; \
    && chown -R agent:agent /app /output /var/lib/mint /home/agent/.cargo

ENV CARGO_HOME=/opt/cargo \
    CARGO_NET_OFFLINE=true \
    RUST_BACKTRACE=1 \
    PATH="/opt/verifier-venv/bin:/usr/local/cargo/bin:${PATH}"

CMD ["sleep", "infinity"]
