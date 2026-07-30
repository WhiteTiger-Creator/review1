FROM public.ecr.aws/docker/library/ruby:3.3-slim-bookworm@sha256:e76733e94b3a5893e4a141024ef3a583dc10781dc24becebf74f9c9f9a33e3df

WORKDIR /app

# verifier-bake-v2: offline pytest in /opt/verifier
RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    python3=3.11.2-1+b1 \
    python3-pip=23.0.1+dfsg-1 \
    python3-venv=3.11.2-1+b1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        pytest-randomly==3.16.0

ENV PATH=/opt/verifier/bin:${PATH}

RUN mkdir -p /app/output /logs/verifier /logs/agent

COPY . /app/environment

RUN chmod +x /app/environment/exec/tacts

ENV RUBYLIB=/app/environment:/app/environment/lib:/app/environment/lib/core:/app/environment/ax:/app/environment/by:/app/environment/cz:/app/environment/ez:/app/environment/qx
ENV PATH=/app/environment/exec:${PATH}
