FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d AS ochre_panel_room

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       bash \
       make \
       perl \
       python3 \
       python3-pip \
       python3-venv \
       coreutils \
       findutils \
       gawk \
       tmux \
       asciinema \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
COPY wheels /tmp/wheels
RUN sed -i 's/\r$//' /tmp/requirements.lock \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --no-index --find-links=/tmp/wheels --require-hashes -r /tmp/requirements.lock \
    && rm -rf /tmp/wheels /tmp/requirements.lock \
    && ln -sf /opt/venv/bin/pytest /usr/local/bin/pytest \
    && ln -sf /opt/venv/bin/python /usr/local/bin/verifier-python

COPY app/ /app/

RUN find /app -type f \( -name '*.pl' -o -name '*.pm' -o -name '*.tsv' -o -name '*.txt' -o -name '*.md' -o -name 'Makefile' \) \
        -exec sed -i 's/\r$//' {} + \
    && mkdir -p /app/out /app/notes \
    && printf '\n' > /app/out/.keep \
    && printf '\n' > /app/notes/.keep \
    && test -f /app/lamps/smoke/operators.tsv \
    && test -f /app/lamps/smoke/widths.tsv \
    && make -C /app clean \
    && make -C /app dispatch PANEL=/app/lamps/smoke OUT=/app/out \
    && test -f /app/out/beacon.queue \
    && test -f /app/out/runner.fold \
    && make -C /app clean

CMD ["sleep", "infinity"]
