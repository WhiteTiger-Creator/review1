FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      g++=4:12.2.0-3 \
      curl=7.88.1-10+deb12u15 \
      ca-certificates=20230311+deb12u1 \
      procps=2:4.0.2-3 \
      tmux=3.3a-3 \
      asciinema=2.2.0-1 \
 && rm -rf /var/lib/apt/lists/*
# Single stage on purpose. g++ has to stay in the runtime image because the
# agent compiles the tool inside the container and the verifier re-runs that
# same binary against journals it generates at verify time, so there is no
# build artefact a builder stage could hand over.

# Generic verifier tooling only, pytest plus a CTRF reporter. It reveals nothing
# about grading: the test logic lives under /tests and is mounted at verify time.
COPY requirements.lock /tmp/requirements.lock
RUN python -m venv /opt/verifier-venv \
 && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
 && rm -f /tmp/requirements.lock

WORKDIR /app

COPY hypersomnia /app/hypersomnia
COPY docs /app/docs
COPY journal /app/journal
COPY banlist /app/banlist
COPY msconfig.json /app/msconfig.json

CMD ["/bin/bash"]
