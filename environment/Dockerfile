FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV GOTOOLCHAIN=local \
    GOPROXY=off \
    GOFLAGS=-mod=mod \
    CGO_ENABLED=0

COPY requirements.lock /tmp/requirements.lock

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes \
        -r /tmp/requirements.lock

RUN go build std

# Debian's root login profile replaces PATH, which otherwise hides the Go
# toolchain from tmux/login shells used by interactive agents.
RUN ln -s /usr/local/go/bin/go /usr/local/bin/go \
    && ln -s /usr/local/go/bin/gofmt /usr/local/bin/gofmt

WORKDIR /app
COPY task_file/ /app/
RUN python3 -c 'import base64,gzip,json,pathlib; p=pathlib.Path("/app/input/match.json"); d=json.loads(p.read_text()); load=lambda n:gzip.decompress(base64.b64decode(pathlib.Path(n).read_text())).decode(); d["official_handbook"]=load("/app/ABALONE_HANDBOOK.seal")+"\n\n"+load("/app/STRATEGY_APPENDIX.seal")+"\n\n"+pathlib.Path("/app/TEMPO_APPENDIX.md").read_text(); p.write_text(json.dumps(d,indent=2)+"\n")' \
    && rm /app/ABALONE_HANDBOOK.seal /app/STRATEGY_APPENDIX.seal /app/TEMPO_APPENDIX.md \
    && mkdir -p /app/output

CMD ["sleep", "infinity"]
