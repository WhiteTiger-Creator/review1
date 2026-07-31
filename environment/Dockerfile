FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

RUN apt-get update \
    && apt-get install -y --allow-downgrades --no-install-recommends \
        tmux \
        asciinema \
        curl \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
        g++ \
        make \
        build-essential \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash agent \
    && mkdir -p /tmp/pytest_cache \
    && chmod 1777 /tmp/pytest_cache

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && /opt/verifier-venv/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock

WORKDIR /app

COPY --chown=agent:agent docs/ /app/docs/
COPY --chown=agent:agent fixtures/ /app/fixtures/
COPY --chown=agent:agent contracts/ /app/contracts/
COPY --chown=agent:agent Makefile /app/
COPY --chown=agent:agent include/ /app/include/
COPY --chown=agent:agent src/ /app/src/
COPY --chown=agent:agent walk/ /app/walk/
COPY --chown=agent:agent kernel/ /app/kernel/
COPY --chown=agent:agent numeric/ /app/numeric/
COPY --chown=agent:agent policy/ /app/policy/
COPY --chown=agent:agent catalog/ /app/catalog/
COPY --chown=agent:agent vendor/ /app/vendor/
COPY --chown=agent:agent scripts/ /app/scripts/
COPY verifier-only/ /tmp/verifier-only/

RUN mkdir -p /app/var/qbound-interval-store /app/var/qbound-cert-ledger /app/output /app/build \
    && chmod +x /app/scripts/*.sh \
    && printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'exec /app/scripts/rebuild-qbound-analyzer.sh "$@"' \
         > /app/rebuild-qbound-analyzer.sh \
    && chmod +x /app/rebuild-qbound-analyzer.sh \
    && /app/scripts/bootstrap-qbound-tool.sh \
    && mkdir -p /opt/verifier-fixtures/tb3 \
    && cp -a /tmp/verifier-only/tb3/poison-pack /opt/verifier-fixtures/tb3/poison-pack \
    && rm -rf /tmp/verifier-only \
    && rm -rf /app/fixtures/tb3 \
    && chown -R agent:agent /app /home/agent \
    && chmod -R u+rwX /app \
    && chmod -R a+rX /opt/verifier-fixtures
