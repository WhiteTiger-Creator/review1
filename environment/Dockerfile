FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    tmux \
    asciinema && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    --require-hashes --no-deps -r /tmp/requirements.lock
WORKDIR /app
COPY --chmod=0777 app/ /app/
RUN mkdir -p /app/bin /app/var/lib/hallowspar && \
    chmod 0777 /app/bin /app/var /app/var/lib /app/var/lib/hallowspar /opt && \
    mkdir -p /opt/go-cache && chmod 0777 /opt/go-cache
ENV GOFLAGS=-mod=mod
ENV GOCACHE=/opt/go-cache
ENV GOTOOLCHAIN=local
ENV CGO_ENABLED=0
ENV GOPROXY=off
ENV GOSUMDB=off
ENV PATH=/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN ln -sf /usr/local/go/bin/go    /usr/bin/go && \
    ln -sf /usr/local/go/bin/gofmt /usr/bin/gofmt && \
    printf 'export PATH=/usr/local/go/bin:/go/bin:$PATH\nexport GOCACHE=/opt/go-cache\nexport GOPROXY=off\nexport GOSUMDB=off\nexport GOFLAGS=-mod=mod\nexport GOTOOLCHAIN=local\nexport CGO_ENABLED=0\n' > /etc/profile.d/go.sh && \
    chmod 0644 /etc/profile.d/go.sh && \
    printf '\nif ! command -v go >/dev/null 2>&1; then export PATH=/usr/local/go/bin:/go/bin:$PATH; fi\nexport GOCACHE=/opt/go-cache\nexport GOPROXY=off\nexport GOSUMDB=off\nexport GOFLAGS=-mod=mod\nexport GOTOOLCHAIN=local\nexport CGO_ENABLED=0\n' >> /etc/bash.bashrc
CMD ["/bin/bash"]
