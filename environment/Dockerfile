FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC \
    LC_ALL=C.UTF-8 \
    RT_CLOCK=/app/config/clock

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
        sqlite3=3.40.1-2+deb12u2 \
        jq=1.6-2.1+deb12u2 \
        patch=2.7.6-7 \
        procps=2:4.0.2-3 \
        util-linux=2.38.1-5+deb12u3 \
        ca-certificates=20230311+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

COPY app /app
COPY data /tmp/task-data
COPY entrypoint.sh /usr/local/bin/rt-entrypoint.sh

RUN pip install --no-cache-dir \
        "cryptography==43.0.0" \
        "pyyaml==6.0.2" \
        "pytest==8.4.1" \
        "pytest-json-ctrf==0.3.5"
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/bin /app/state/cache /var/log/rt-daemon /output/rt-runs \
    && printf '%s\n' '#!/bin/sh' 'exec python3 -m rt_core.cli hostd "$@"' > /app/bin/rt-daemon \
    && printf '%s\n' '#!/bin/sh' 'exec python3 -m rt_core.cli run "$@"' > /app/bin/rt-run \
    && printf '%s\n' '#!/bin/sh' 'exec python3 -m rules_svc.cli "$@"' > /app/bin/rulesctl \
    && printf '%s\n' '#!/bin/sh' 'exec python3 -m rules_svc.service "$@"' > /app/bin/rules-service \
    && printf '%s\n' '#!/bin/sh' 'exec python3 -m rt_core.cli cachectl "$@"' > /app/bin/rt-cachectl \
    && printf '%s\n' '#!/bin/sh' 'exec python3 -m rt_core.cli fault "$@"' > /app/bin/rt-fault-runner \
    && chmod +x /app/bin/rt-daemon /app/bin/rt-run /app/bin/rulesctl /app/bin/rules-service /app/bin/rt-cachectl /app/bin/rt-fault-runner

RUN python /tmp/task-data/build_fixtures.py --output /data --app /app --seed /tmp/task-data/signing-key.seed \
    && rm -rf /tmp/task-data \
    && chmod a-w /data /data/trust /data/tenants /data/tenants/tenant-a /data/tenants/tenant-b /data/legacy-v1 \
    && chmod a-w /data/trust/doc-signers.pub \
        /data/tenants/tenant-a/notes.txt /data/tenants/tenant-a/.env.json \
        /data/tenants/tenant-b/notes.txt /data/tenants/tenant-b/.env.json \
        /data/legacy-v1/behavior.json

RUN useradd -u 1000 -m agent || true \
    && useradd -u 1100 -M rtdaemon || true \
    && useradd -u 1101 -M rules || true \
    && useradd -u 1201 -M tenant-a || true \
    && useradd -u 1202 -M tenant-b || true

RUN chmod +x /usr/local/bin/rt-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/rt-entrypoint.sh"]
CMD ["sleep", "infinity"]
