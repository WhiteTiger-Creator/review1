FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV PATH="/usr/local/go/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    ca-certificates \
    tmux \
    asciinema \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/local/go/bin/go /usr/local/bin/go \
    && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock

WORKDIR /workspace
COPY task_file/ /workspace/task_file/
RUN mkdir -p /workspace/cmd/systemd-window-plan /workspace/bin /workspace/output /logs/verifier \
    && cp /workspace/task_file/cmd/systemd-window-plan/main.go /workspace/cmd/systemd-window-plan/main.go \
    && cd /workspace/cmd/systemd-window-plan \
    && GO111MODULE=off go build -o /workspace/bin/systemd-window-plan . \
    && /workspace/bin/systemd-window-plan /workspace/task_file/window_request.json /workspace/output/window_plan.json
