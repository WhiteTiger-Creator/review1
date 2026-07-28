# force-rebuild 2026-07-19-v43-reward-block-fix
# force-rebuild 2026-07-19-infra-retry-v46
# force-rebuild 2026-07-20-v48-p50-spec-fix
# force-rebuild 2026-07-21-v56-stub-removal-doc-rename
# force-rebuild 2026-07-23-v56-regional-tier-driver
# force-rebuild 2026-07-24-v56-dockerfile-hygiene
# force-rebuild 2026-07-24-v57-audit-credit-ledger-driver
# force-rebuild 2026-07-27-v59-login-shell-go-path
FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3=3.* \
    tmux \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-report==1.5.0 pytest-json-ctrf==0.3.5 asciinema==2.4.0

# Debian login shells replace the image-level PATH in /etc/profile. Keep the
# toolchain visible both through the default login PATH and through profile.d.
RUN ln -sf /usr/local/go/bin/go /usr/local/bin/go \
    && ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt \
    && printf '%s\n' 'export PATH="/usr/local/go/bin:/go/bin:$PATH"' \
        > /etc/profile.d/00-go-path.sh \
    && chmod 0644 /etc/profile.d/00-go-path.sh

ENV GOFLAGS=-mod=mod
ENV GOPROXY=https://proxy.golang.org,direct

ENV TASK_VERSION=v59-login-shell-go-path

WORKDIR /app

# Dependency-install layer: copy only the module manifest (plus the
# throwaway warmup source) so `go mod download` is cached independently of
# the agent's later source authoring, and group both install RUN steps
# contiguously with no COPY between them.
COPY source/go.mod ./
# Warm the module cache with the FULL transitive closure (go.mod's require
# list alone doesn't pull transitive deps like modernc.org/libc without an
# actual build). modcache-warmup.go is throwaway: built once here, reusing
# the real go.mod so it resolves against the same requires, then deleted so
# no application source ships in the final image.
COPY scripts/modcache-warmup.go /tmp/modwarm/main.go
RUN go mod download \
    && cp /app/go.mod /tmp/modwarm/go.mod \
    && cd /tmp/modwarm && go build -o /dev/null . \
    && rm -rf /tmp/modwarm

# NOTE: the golang toolchain is intentionally kept in the runtime image
# (not split into a multi-stage build) because the agent must author and
# compile main.go themselves inside this exact container; no pre-built
# source ships here for the agent to edit in place.
ENV GOPROXY=off

COPY docs/ /docs/
