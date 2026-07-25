FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

RUN apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
        asciinema bash ca-certificates python3 python3-venv tmux \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /opt/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes --no-deps -r /opt/requirements.lock
WORKDIR /app
COPY main.go /app/main.go
COPY task_file/ /app/task_file/
RUN mkdir -p /app/bin \
    && command -v go \
    && command -v tmux \
    && command -v asciinema \
    && /opt/verifier-venv/bin/python -m pytest --version
