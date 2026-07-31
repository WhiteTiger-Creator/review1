FROM public.ecr.aws/docker/library/rust:1.85-slim@sha256:9f841bbe9e7d8e37ceb96ed907265a3a0df7f44e3737d0b100e7907a679acb36

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    patch=2.7.6-7 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        pytest-randomly==3.16.0
ENV PATH="/opt/verifier/bin:${PATH}"

COPY . /app/environment

RUN chmod +x /app/environment/scripts/refresh_join.sh \
    && mkdir -p /app/output/local_chk \
    && /app/environment/scripts/refresh_join.sh \
    && rm -rf /app/environment/target

WORKDIR /app
