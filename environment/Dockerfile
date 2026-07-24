FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        less \
        nano \
        procps \
        python3 \
        python-is-python3 \
        python3-pip \
        python3-venv \
        tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm -f /tmp/requirements.lock

COPY task_file/scan_input /app/task_file/scan_input
COPY task_file/abi_transition_runbook.md /app/task_file/abi_transition_runbook.md
COPY task_file/model.py /app/task_file/model.py
RUN rm -rf /app/task_file/output && mkdir -p /app/task_file/output
