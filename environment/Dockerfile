FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

COPY apt-preferences /etc/apt/preferences.d/task-pins
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates r-base-core tmux asciinema python3 python3-venv util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

RUN groupadd --gid 1000 taskagent \
    && useradd --uid 1000 --gid taskagent --create-home --shell /bin/bash taskagent

WORKDIR /app
COPY --chown=taskagent:taskagent analysis.R /app/analysis.R
COPY --chmod=0755 run.sh /app/run.sh
COPY data/ /app/data/
COPY docs/ /app/docs/
RUN mkdir -p /app/outputs \
    && chown taskagent:taskagent /app/outputs

ENV HOME=/home/taskagent USER=taskagent LOGNAME=taskagent
ENTRYPOINT ["/usr/bin/setpriv", "--reuid=1000", "--regid=1000", "--init-groups", "--no-new-privs"]
