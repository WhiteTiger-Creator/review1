FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:f3a68cf41a855d227d1b0ab832bed9749469ef38cf4f58182fb8c893bc462383

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    openssl=3.0.17-1~deb12u2 \
    patch=2.7.6-7 \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier

COPY requirements.txt /tmp/requirements.txt
RUN /opt/verifier/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.txt

COPY docs /app/environment/docs
COPY irc /app/environment/irc

RUN chmod +x /app/environment/irc/cmd/irc \
    && mkdir -p /app/environment/irc/state /app/output \
    && cp -a /app/environment/irc/fixtures/. /app/environment/irc/state/

ENV PATH="/opt/verifier/bin:${PATH}"
