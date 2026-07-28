FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema \
    tmux \
    make \
    patch \
    && rm -rf /var/lib/apt/lists/*

COPY verifier-requirements.lock /tmp/verifier-requirements.lock

RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir -r /tmp/verifier-requirements.lock

ENV PATH="/opt/verifier-venv/bin:${PATH}"
ENV PYTHONPATH=/app

WORKDIR /app
COPY app/ /app/

RUN make build \
    && mkdir -p /app/fixtures /app/output \
    && python3 /app/scripts/gen_fixtures.py \
    && rm -f /app/scripts/gen_fixtures.py

CMD ["/bin/bash"]
