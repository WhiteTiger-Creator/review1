FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:f3a68cf41a855d227d1b0ab832bed9749469ef38cf4f58182fb8c893bc462383

ENV DEBIAN_FRONTEND=noninteractive \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_UPDATE_NOTIFIER=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    python3=3.11.2-1+b1 \
    python3-venv=3.11.2-1+b1 \
    ca-certificates=20230311+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        pytest-randomly==3.16.0
RUN ln -sf /opt/verifier/bin/pytest /usr/local/bin/pytest
ENV PATH=/opt/verifier/bin:${PATH}

WORKDIR /app/environment
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit \
    && npm cache clean --force

COPY . .
RUN ./node_modules/.bin/tsc -p tsconfig.json \
    && mkdir -p /app/output /logs/verifier \
    && rm -rf /root/.npm /tmp/*

WORKDIR /app
CMD ["node", "-e", "console.log('vault environment ready')"]
