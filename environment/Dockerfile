# Digest-pinned canonical Ruby bookworm base.
FROM ruby:3.3-slim-bookworm@sha256:e76733e94b3a5893e4a141024ef3a583dc10781dc24becebf74f9c9f9a33e3df

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3=3.11.2-1+b1 \
        python3-venv=3.11.2-1+b1 \
        ca-certificates=20230311+deb12u1 \
        libssl3=3.0.20-1~deb12u2 \
        sqlite3=3.40.1-2+deb12u2 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        pytest-randomly==3.16.0

ENV PATH=/opt/verifier/bin:${PATH}

COPY . /app/environment

RUN sqlite3 /app/environment/db/shift_ledger_seed.db < /app/environment/db/shift_ledger_seed.sql \
    && mkdir -p /app/output /app/environment/tools \
    && chmod +x /app/environment/scripts/compile_lane.sh \
    && /app/environment/scripts/compile_lane.sh

CMD ["bash"]
