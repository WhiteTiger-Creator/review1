# Multi-stage Go build. Final runtime uses the canonical
# public.ecr.aws python:3.13-slim-bookworm image
# (dockerfile and image best practices.mdc §2).
# Builder uses the canonical golang:1.24-bookworm image.
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS gobuilder

WORKDIR /src

COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
COPY x0 ./x0
COPY x1 ./x1
COPY x2 ./x2
COPY x3 ./x3
RUN go build -o /tmp/trust_desk ./cmd/trust_desk

FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

LABEL org.opencontainers.image.source="https://github.com/laude-institute/terminal-bench" \
      org.opencontainers.image.title="dnssec-cds-trust-cutover" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="task-local" \
      org.opencontainers.image.created="2026-07-21"

WORKDIR /app

# OS packages (one apt transaction; pinned versions) + agent session dirs
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -m 1777 /tmp \
    && install -d -m 0777 /tmp/.config/asciinema \
    && mkdir -p /app/bin /app/output

# Verifier + agent session tooling (pinned; offline verifier)
RUN pip install --no-cache-dir \
    asciinema==2.4.0 \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

# Prebuilt binary + Go toolchain for offline agent rebuilds
COPY --from=gobuilder /tmp/trust_desk /app/bin/trust_desk
COPY --from=gobuilder /usr/local/go /usr/local/go

# Manifests then sources (least → most volatile)
COPY go.mod /app/go.mod
COPY cmd /app/cmd
COPY internal /app/internal
COPY x0 /app/x0
COPY x1 /app/x1
COPY x2 /app/x2
COPY x3 /app/x3
COPY data /app/data
COPY docs /app/docs
COPY --chmod=0755 scripts /app/scripts

ENV PATH="/usr/local/go/bin:/app/bin:${PATH}" \
    GOMODCACHE=/go/pkg/mod \
    TERM=xterm-256color \
    TMUX_TMPDIR=/tmp

# Login shells (tmux default pane) re-source /etc/profile, which resets PATH.
# Persist agent toolchain paths so `go` and `trust_desk` resolve by name.
RUN printf '%s\n' \
        'export PATH="/usr/local/go/bin:/app/bin:${PATH}"' \
        'export GOMODCACHE=/go/pkg/mod' \
        'export TERM=xterm-256color' \
        'export TMUX_TMPDIR=/tmp' \
        > /etc/profile.d/tbench-agent-path.sh \
    && chmod 644 /etc/profile.d/tbench-agent-path.sh

RUN bash /app/scripts/build.sh \
    && command -v tmux >/dev/null \
    && command -v asciinema >/dev/null \
    && bash -lc 'command -v go >/dev/null && command -v trust_desk >/dev/null'
