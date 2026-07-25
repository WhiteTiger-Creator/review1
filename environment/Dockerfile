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

COPY requirements.lock /tmp/requirements.txt
RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.txt
RUN rm -f /tmp/requirements.txt

ENV PATH=/opt/verifier/bin:${PATH}

RUN mkdir -p /app/output /app/environment

COPY Gemfile /app/environment/Gemfile
COPY briar /app/environment/briar
COPY db /app/environment/db
COPY docs /app/environment/docs
COPY fixtures /app/environment/fixtures
COPY flume /app/environment/flume
COPY kerf /app/environment/kerf
COPY scripts /app/environment/scripts
COPY tools /app/environment/tools

RUN sqlite3 /app/environment/db/shift_ledger_seed.db < /app/environment/db/shift_ledger_seed.sql \
    && chmod +x /app/environment/scripts/compile_lane.sh \
    && /app/environment/scripts/compile_lane.sh

CMD ["bash"]
