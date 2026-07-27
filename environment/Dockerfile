FROM public.ecr.aws/docker/library/ruby:3.3-slim-bookworm@sha256:e76733e94b3a5893e4a141024ef3a583dc10781dc24becebf74f9c9f9a33e3df

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    ca-certificates=20230311+deb12u1 \
    openssl=3.0.20-1~deb12u2 \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        pyyaml==6.0.2

ENV PATH=/opt/verifier/bin:${PATH}

RUN ln -sf /opt/verifier/bin/pytest /usr/local/bin/pytest

COPY Gemfile Gemfile.lock /app/environment/
COPY docs/ /app/environment/docs/
COPY data/ /app/environment/data/
COPY fixtures/ /app/environment/fixtures/
COPY tools/ /app/environment/tools/
COPY n4k/ /app/environment/n4k/
COPY p8m/ /app/environment/p8m/
COPY w2t/ /app/environment/w2t/
COPY r6x/ /app/environment/r6x/
COPY jr8/ /app/environment/jr8/
COPY rp5/ /app/environment/rp5/
COPY ovk/ /app/environment/ovk/
COPY q3z/ /app/environment/q3z/

RUN chmod +x /app/environment/tools/kw_run /app/environment/tools/hex_dgst \
    && mkdir -p /app/output \
    && ln -sf /app/environment/tools/kw_run /usr/local/bin/kw_run

WORKDIR /app
ENV KW_ROOT=/app/environment
ENV KW_OUT=/app/output
