# Dropforge engine-reconstruction task (Node).
#
# Ships the basic rules card and the recorded games under /app. The
# agent writes /app/engine.js to replay a drop script to the final well.
# Everything runs offline: Node is the working language, and Python is present
# only so the test suite can drive the program and compare records.
#
# Canonical Debian base, digest-pinned.
FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

# Node for the task, tmux + asciinema for the agent runtime, and a Python 3
# for the test suite. Installed at build time (build has network) so the task
# runs fully offline afterwards. Debian ships the interpreter as `nodejs`;
# add a `node` on PATH so the documented command works.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        nodejs \
        python3 \
        python3-venv \
        tmux \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/nodejs /usr/local/bin/node

# Python only needs pytest to run the program and compare numbers; no
# numerical libraries are installed, so the math cannot be shifted out of
# Node. Pinned and baked in now; nothing is fetched later.
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5
ENV PATH="/opt/venv/bin:${PATH}"

# The basic rules card and the recorded games (script, final well, score).
COPY rules.md /app/rules.md
COPY games /app/games

WORKDIR /app
