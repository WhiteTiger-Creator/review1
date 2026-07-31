FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

# Base image justification (non-canonical for the task language by design):
# The verifier harness is pytest (tests/test.sh -> python -m pytest), so Python must be
# the image's primary runtime that orchestrates grading. The agent deliverable is a small
# pure-JavaScript file run through a thin Node CLI, so Node.js is added on top via apt.
# Starting from a Node base would still require installing Python + pytest, producing a
# larger image for the same result; the canonical, digest-pinned Python base plus apt
# Node.js is the minimal single-container image covering both runtimes. allow_internet =
# false at run time, so every verifier dependency is installed here with pinned versions.
# Node.js is the Debian bookworm package; the build is reproducible from the pinned base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        tmux \
        nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf "$(command -v nodejs)" /usr/local/bin/node

RUN python -m pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

WORKDIR /app

COPY app/ /app/
